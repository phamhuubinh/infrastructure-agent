"""DR1-703: Claim grounding validator.

Checks that numeric values, target names, and severity words in a model's
assessment response text are traceable to the facts/findings the model was
given. This is not a full semantic theorem prover — it blocks the clear,
dangerous mismatch patterns (invented numbers, invented targets) rather than
proving every sentence correct.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.pipeline.assessment_request import AssessmentRequest

# Numbers with a unit Orion cares about: percent, bytes-ish units, counts.
_NUMERIC_CLAIM = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>%|percent|gb|mb|kb|tb|giây|phút|giờ|seconds?|minutes?|hours?)",
    re.IGNORECASE,
)

# Vietnamese/English hostname-like tokens: word.word, word-word, or an
# explicit "server <name>" / "máy <name>" mention.
_TARGET_MENTION = re.compile(
    r"\b(?:server|máy chủ|máy|host|target)\s+([a-zA-Z0-9][\w.-]{2,63})",
    re.IGNORECASE,
)

# Current-information answers have a tighter contract than ordinary
# infrastructure assessments: a version/date/price/office-holder must be
# visible in the extracted page text, not merely accompanied by a URL footer.
_CURRENT_VERSION = re.compile(r"\b\d+(?:\.\d+){1,3}(?:[-+][\w.-]+)?\b")
_CURRENT_DATE = re.compile(
    r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|"
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|"
    r"july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2},?\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
_CURRENT_PRICE = re.compile(
    r"(?:[$€£]\s*\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s*" r"(?:usd|vnd|eur|gbp)\b)",
    re.IGNORECASE,
)
_OFFICE_HOLDER = re.compile(
    r"\b(?:CEO|chief executive officer)\b.{0,80}?\b(?:is|là)\s+"
    r"(?P<name>[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){1,3})",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ClaimValidationResult:
    """Outcome of grounding a response against allowed facts/findings."""

    grounded: bool
    ungrounded_numbers: tuple[str, ...] = ()
    ungrounded_targets: tuple[str, ...] = ()

    @property
    def violations(self) -> tuple[str, ...]:
        return (*self.ungrounded_numbers, *self.ungrounded_targets)


def _allowed_numeric_tokens(request: AssessmentRequest) -> set[str]:
    tokens: set[str] = set()
    for fact in request.facts:
        if not fact.usable:
            continue
        value = fact.value
        if isinstance(value, (int, float)):
            tokens.add(_normalize_number(value))
        elif isinstance(value, str):
            for match in re.finditer(r"\d+(?:[.,]\d+)?", value):
                tokens.add(_normalize_number(match.group(0)))
    for finding in request.findings:
        tokens.add(_normalize_number(finding.score))
    return tokens


def _normalize_number(value: object) -> str:
    text = str(value).replace(",", ".").rstrip("0").rstrip(".")
    return text or "0"


def _allowed_targets(request: AssessmentRequest) -> set[str]:
    targets: set[str] = set()
    for fact in request.facts:
        targets.add(fact.target.lower())
    for package in request.evidence:
        target = getattr(package, "target", None)
        if target:
            targets.add(str(target).lower())
    frame = request.request_frame
    if frame:
        resolved = frame.get("target_resolved")
        if resolved:
            targets.add(str(resolved).lower())
        raw = frame.get("target_raw")
        if raw:
            targets.add(str(raw).lower())
    return targets


class ClaimValidator:
    """Validate that response text only makes claims grounded in evidence."""

    def validate(
        self, response_text: str, assessment_request: AssessmentRequest
    ) -> ClaimValidationResult:
        if not assessment_request.has_grounded_evidence:
            # Nothing to ground against — do not accuse the model of
            # hallucinating a number when we handed it no facts at all;
            # that is an evidence-completeness problem, not a claim problem.
            return ClaimValidationResult(grounded=True)

        allowed_numbers = _allowed_numeric_tokens(assessment_request)
        ungrounded_numbers: list[str] = []
        for match in _NUMERIC_CLAIM.finditer(response_text):
            normalized = _normalize_number(match.group("value"))
            if normalized not in allowed_numbers:
                ungrounded_numbers.append(match.group(0))

        allowed_targets = _allowed_targets(assessment_request)
        ungrounded_targets: list[str] = []
        if allowed_targets:
            for match in _TARGET_MENTION.finditer(response_text):
                candidate = match.group(1).lower().rstrip(".,")
                if candidate not in allowed_targets and not any(
                    candidate in target or target in candidate
                    for target in allowed_targets
                ):
                    ungrounded_targets.append(match.group(1))

        grounded = not ungrounded_numbers and not ungrounded_targets
        return ClaimValidationResult(
            grounded=grounded,
            ungrounded_numbers=tuple(dict.fromkeys(ungrounded_numbers)),
            ungrounded_targets=tuple(dict.fromkeys(ungrounded_targets)),
        )


def redact_ungrounded_claims(
    response_text: str, assessment_request: AssessmentRequest, *, lang: str = "vi"
) -> str:
    """Replace ungrounded numeric/target claims in place with a marker.

    Unlike :meth:`ClaimValidator.validate`, which only reports violations,
    this rewrites the offending substrings so the shipped response cannot
    carry an invented number or target forward, while leaving everything
    else the model said intact.
    """

    if not assessment_request.has_grounded_evidence:
        return response_text

    marker = "[số liệu chưa xác nhận]" if lang == "vi" else "[unverified figure]"
    target_marker = (
        "[mục tiêu chưa xác nhận]" if lang == "vi" else "[unverified target]"
    )

    allowed_numbers = _allowed_numeric_tokens(assessment_request)

    def _replace_number(match: re.Match[str]) -> str:
        normalized = _normalize_number(match.group("value"))
        if normalized in allowed_numbers:
            return match.group(0)
        return marker

    redacted = _NUMERIC_CLAIM.sub(_replace_number, response_text)

    allowed_targets = _allowed_targets(assessment_request)
    if allowed_targets:

        def _replace_target(match: re.Match[str]) -> str:
            candidate = match.group(1).lower().rstrip(".,")
            if candidate in allowed_targets or any(
                candidate in target or target in candidate for target in allowed_targets
            ):
                return match.group(0)
            return match.group(0).replace(match.group(1), target_marker)

        redacted = _TARGET_MENTION.sub(_replace_target, redacted)

    return redacted


def redact_ungrounded_external_claims(
    response_text: str,
    assessment_request: AssessmentRequest,
    *,
    lang: str = "vi",
) -> str:
    """Redact current claims absent from extracted external content.

    The normal numeric guard is intentionally broad and applies to every
    assessment.  This additional guard only applies to the external route and
    compares user-visible current claims with the actual page content handed
    to the model.  A fetch receipt or source URL alone is not grounding.

    GA2-R1-02: Grounding now consumes **selected passages** from SUFFICIENT
    documents rather than the full fetched page corpus.  This ensures that
    a value occurring elsewhere in the same page (but outside the selected
    request-relevant passage) cannot ground the wrong claim.

    GA2-R1-B: Only documents with relevance == "sufficient" AND passages with
    relevance == "sufficient" are included in the grounding corpus.  PARTIAL
    or IRRELEVANT documents (and their passages) must NOT be used to ground
    concrete current claims (version, date, price, identity).  This prevents
    the model from promoting partial evidence to verified status.

    GA2-R1-02 Subject binding: A concrete claim is groundable only when its
    subject/claim type/value are supported by the selected passage used for
    that request.  The subject extraction generalizes beyond a hard-coded
    product-name list to handle simple factual questions about arbitrary
    subjects when the user supplies an explicit URL.

    No fallback to full document content: when selected_passages exist (even
    if empty or all PARTIAL/IRRELEVANT), the full document content is NEVER
    used for grounding.  This enforces that only request-relevant excerpts
    can ground claims.
    """

    if assessment_request.intent != "EXTERNAL_VERIFICATION":
        return response_text

    # Extract the requested subject from the raw request for subject binding.
    requested_subject = _extract_requested_subject(
        assessment_request.raw_request.casefold()
    )

    # Build grounding corpus from SUFFICIENT passages of SUFFICIENT documents only.
    # GA2-R1-02: When selected_passages exist (even if empty), NEVER fall back
    # to full document content. This enforces passage-only grounding.
    corpus_parts: list[str] = []
    for package in assessment_request.evidence:
        data = getattr(package, "data", None)
        if not isinstance(data, dict):
            continue
        documents = data.get("documents")
        if not isinstance(documents, list):
            continue
        for document in documents:
            if not isinstance(document, dict):
                continue
            # GA2-R1-B: Only ground claims against SUFFICIENT relevance documents
            relevance = document.get("relevance", "irrelevant")
            if relevance != "sufficient":
                continue
            # GA2-R1-02: Check if selected_passages exist for this document
            passages = document.get("selected_passages")
            if isinstance(passages, list):
                for passage in passages:
                    if not isinstance(passage, dict):
                        continue
                    # GA2-R1-B: Only SUFFICIENT passages can ground claims
                    passage_relevance = passage.get("relevance", "irrelevant")
                    if passage_relevance != "sufficient":
                        continue
                    passage_text = passage.get("text")
                    if passage_text is None:
                        continue
                    passage_text = str(passage_text)
                    # GA2-R1-02: Subject binding - if a specific subject is
                    # requested, verify the passage mentions that subject
                    if requested_subject:
                        if not re.search(
                            rf"\b{re.escape(requested_subject)}\b",
                            passage_text,
                            re.IGNORECASE,
                        ):
                            # Subject not in this passage - skip it
                            continue
                    corpus_parts.append(passage_text)
            elif document.get("content") is not None:
                # Only use full content when NO selected_passages field exists
                # (backward compatibility with older evidence packages).
                # When passages exist (even empty), we enforce passage-only.
                corpus_parts.append(str(document["content"]))

    corpus = "\n".join(corpus_parts).casefold()

    marker = (
        "[thông tin hiện tại chưa xác nhận]"
        if lang == "vi"
        else "[unverified current claim]"
    )

    def _replace_version_if_absent(match: re.Match[str]) -> str:
        """Keep an exact verified version or a safe container-image variant.

        A verified release such as ``3.14.2`` is commonly rendered as
        ``python:3.14.2-slim`` in a generated Dockerfile.  The selected
        passage normally contains the release value, not every image-tag
        suffix.  Accept that narrow representation only for the requested
        subject; do not use it as a general rewrite/allow-list for unrelated
        version-like strings elsewhere in an artifact.
        """

        claimed = match.group(0)
        if claimed.casefold() in corpus:
            return claimed

        base_version = re.match(r"\d+(?:\.\d+){1,3}", claimed)
        if base_version is None or base_version.group(0).casefold() not in corpus:
            if _is_non_claim_artifact_version(response_text, match):
                return claimed
            return marker
        if not requested_subject or claimed == base_version.group(0):
            return marker

        image_reference = re.compile(
            rf"\b{re.escape(requested_subject)}:{re.escape(claimed)}\b",
            re.IGNORECASE,
        )
        return claimed if image_reference.search(response_text) else marker

    guarded = _CURRENT_VERSION.sub(_replace_version_if_absent, response_text)

    def _replace_if_absent(match: re.Match[str]) -> str:
        return match.group(0) if match.group(0).casefold() in corpus else marker

    guarded = _CURRENT_DATE.sub(_replace_if_absent, guarded)
    guarded = _CURRENT_PRICE.sub(_replace_if_absent, guarded)

    def _replace_office_holder(match: re.Match[str]) -> str:
        name = match.group("name")
        if name.casefold() in corpus:
            return match.group(0)
        return match.group(0).replace(name, marker)

    result = _OFFICE_HOLDER.sub(_replace_office_holder, guarded)

    # If corpus is empty, nothing was grounded — ensure the redaction marker
    # is present when the response contains ungrounded claims.
    if not corpus.strip():
        # If no markers were added and the original text has claims,
        # append a general marker to indicate nothing was verified.
        if marker not in result and (
            _CURRENT_VERSION.search(response_text)
            or _CURRENT_DATE.search(response_text)
            or _CURRENT_PRICE.search(response_text)
            or _OFFICE_HOLDER.search(response_text)
        ):
            return f"{result} [{lang == 'vi' and 'chưa xác nhận' or 'unverified'}]"
    return result


def _is_non_claim_artifact_version(
    response_text: str, match: re.Match[str]
) -> bool:
    """Recognize narrow code/config values that are not current-value claims.

    Package pins and schema labels frequently contain version-shaped values.
    They must remain their own values; an externally verified runtime version
    is not a license to rewrite or redact them.  This deliberately covers
    only reviewed assignment forms, leaving ordinary prose claims subject to
    the external grounding guard.
    """

    line_start = response_text.rfind("\n", 0, match.start()) + 1
    line_end = response_text.find("\n", match.end())
    line = response_text[line_start : None if line_end == -1 else line_end]
    if "==" in line:
        return True
    return bool(
        re.search(
            r"\b(?:schema(?:[_-]?version)?|api[_-]?version)\s*[:=]\s*"
            r"v?\d+(?:\.\d+){1,3}\b",
            line,
            re.IGNORECASE,
        )
    )


def _extract_requested_subject(request_lower: str) -> str | None:
    """Extract a bounded deterministic subject/entity from the request.

    Returns the requested subject (e.g., "python", "postgresql",
    "kubernetes", or an arbitrary subject from an explicit-URL question)
    or None for generic requests without a named subject.

    GA2-R1-02: Generalized beyond a hard-coded product-name list to handle
    simple factual questions about arbitrary subjects when the user
    supplies an explicit URL or clearly names the entity.
    """
    # Common subjects that indicate a specific entity
    KNOWN_SUBJECTS = [
        "python",
        "postgresql",
        "postgres",
        "mysql",
        "mongodb",
        "kubernetes",
        "k8s",
        "docker",
        "nginx",
        "apache",
        "redis",
        "grafana",
        "zabbix",
        "linux",
        "ubuntu",
        "centos",
        "windows",
        "macos",
        "examplecorp",
        "acme",
    ]

    for subject in KNOWN_SUBJECTS:
        if subject in request_lower:
            return subject

    # GA2-R1-02: Generalized subject extraction for arbitrary subjects.
    # When the request is a simple factual question (version/date/price/
    # identity), try to extract the subject from common patterns:
    # - "version of <subject>" -> extract <subject>
    # - "<subject> version" -> extract <subject>
    # - "phiên bản của <subject>" -> extract <subject>
    # - "<subject> là gì" -> extract <subject>
    # - URL-based questions: extract domain/subject from the URL
    request_type = _detect_request_type(request_lower)
    if request_type != "general":
        # Try pattern-based extraction
        # Pattern: "version of X" or "current version of X"
        match = re.search(r"version\s+(?:of|của)\s+(\w+)", request_lower)
        if match:
            subject = match.group(1)
            if len(subject) >= 2 and len(subject) <= 50:
                return subject

        # Pattern: "X version" (e.g., "python version")
        match = re.search(r"^(\w+)\s+version", request_lower)
        if match:
            subject = match.group(1)
            if len(subject) >= 2 and len(subject) <= 50:
                return subject

        # Pattern: "phiên bản X" or "phiên bản của X"
        match = re.search(r"phiên\s*bản\s+(?:của\s+)?(\w+)", request_lower)
        if match:
            subject = match.group(1)
            if len(subject) >= 2 and len(subject) <= 50:
                return subject

    return None


def _detect_request_type(request_lower: str) -> str:
    """Detect the type of request to determine required claim support.

    Order matters: check specific multi-word patterns BEFORE single-word
    tokens to avoid misclassification.  For example "release date" must
    classify as DATE, not VERSION, even though it contains "release".
    """
    # DATE — check multi-word patterns BEFORE single-word tokens
    if any(kw in request_lower for kw in ("release date", "current date", "date")):
        return "date"
    # VERSION — check before generic "release"
    if any(kw in request_lower for kw in ("current version", "version")):
        return "version"
    # PRICE — check multi-word patterns
    if any(
        kw in request_lower
        for kw in ("current price", "current value", "cost", "price")
    ):
        return "price"
    # IDENTITY — check multi-word patterns
    if any(
        kw in request_lower
        for kw in ("prime minister", "chief executive officer", "office holder")
    ):
        return "identity"
    if any(
        kw in request_lower
        for kw in (
            "holder",
            "officer",
            "identity",
            "ceo",
            "president",
            "chancellor",
            "secretary",
        )
    ):
        return "identity"
    return "general"
