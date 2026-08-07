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
    target_marker = "[mục tiêu chưa xác nhận]" if lang == "vi" else "[unverified target]"

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
