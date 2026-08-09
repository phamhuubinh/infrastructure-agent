"""Small, structured semantic context for deterministic follow-up routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.pipeline.parameter_extractor import ExtractedParams
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.time_range_resolver import TimeRange

if TYPE_CHECKING:
    from src.pipeline.fact_set import FactSet
    from src.pipeline.request_frame import RequestFrame


_INCIDENT_ID = re.compile(
    r"\b(?:INC|INCIDENT|PROBLEM|EVENT|ALERT)[-_:#]?\d+\b", re.IGNORECASE
)

_MAX_EVIDENCE_RECEIPTS = 10


@dataclass(frozen=True, slots=True)
class EvidenceReceipt:
    """GA2-E08: compact record of what was *actually* used to produce the
    previous answer — the actual tool/source/target, never hidden
    chain-of-thought or raw evidence values. This is intentionally distinct
    from ``active_sources`` (what the user allowed/requested): a provenance
    question ("nguồn dữ liệu nào vừa được dùng?") must answer from this, not
    from the request constraint, because a normal request with no hard
    source constraint still actually used *some* real source.
    """

    source: str
    target: str
    capability: str
    fact_ids: tuple[str, ...]
    status: str
    timestamp: str

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "capability": self.capability,
            "fact_ids": list(self.fact_ids),
            "status": self.status,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, value: object) -> EvidenceReceipt | None:
        if not isinstance(value, dict):
            return None
        fact_ids = value.get("fact_ids", ())
        return cls(
            source=str(value.get("source") or ""),
            target=str(value.get("target") or ""),
            capability=str(value.get("capability") or ""),
            fact_ids=(
                tuple(str(item) for item in fact_ids if str(item))
                if isinstance(fact_ids, (list, tuple))
                else ()
            ),
            status=str(value.get("status") or ""),
            timestamp=str(value.get("timestamp") or ""),
        )


def build_evidence_receipts(
    fact_set: FactSet, *, status: str
) -> tuple[EvidenceReceipt, ...]:
    """GA2-E08: derive compact evidence receipts from the facts an
    investigation actually collected, grouped by (source, target,
    capability). This is the *actual* origin of the answer, independent of
    whether the user stated a hard source constraint for the request.
    """
    if not fact_set.facts:
        return ()
    now = datetime.now(timezone.utc).isoformat()
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for fact in fact_set.facts:
        provenance = getattr(fact, "provenance", None)
        capability = getattr(provenance, "capability", "") if provenance else ""
        key = (fact.source, fact.target, capability)
        grouped.setdefault(key, []).append(fact.id)
    return tuple(
        EvidenceReceipt(
            source=source,
            target=target,
            capability=capability,
            fact_ids=tuple(fact_ids),
            status=status,
            timestamp=now,
        )
        for (source, target, capability), fact_ids in grouped.items()
    )


@dataclass(frozen=True, slots=True)
class SessionInvestigationContext:
    """Only semantic routing state; never raw evidence or model summaries."""

    active_target: str | None = None
    active_concept: str | None = None
    active_service: str | None = None
    active_path: str | None = None
    active_time_range: TimeRange | None = None
    incident_ids: tuple[str, ...] = ()
    active_sources: tuple[SourceConstraint, ...] = ()
    active_excluded_sources: tuple[SourceConstraint, ...] = ()
    # GA2-D08: requested answer shape affects response construction only.
    requested_answer_shape: str = "DEFAULT"  # DEFAULT | SHORT | RAW | EXPLAIN_PREVIOUS
    # GA2-E02: the field name (e.g. "target") the system just asked the
    # user to clarify, if any. Lets the next short reply be resolved as
    # *answering that question* — with whatever constraints (e.g. a hard
    # source restriction) were already established before the question was
    # asked — rather than being parsed as an unrelated new request.
    pending_clarification_field: str | None = None
    # GA2-E08: what was *actually* used to produce the previous answer(s),
    # most-recent-last, capped to bound growth. Never raw evidence values.
    previous_evidence_receipts: tuple[EvidenceReceipt, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "active_target": self.active_target,
            "active_concept": self.active_concept,
            "active_service": self.active_service,
            "active_path": self.active_path,
            "active_time_range": (
                self.active_time_range.to_dict() if self.active_time_range else None
            ),
            "incident_ids": list(self.incident_ids),
            "active_sources": [source.name for source in self.active_sources],
            "active_excluded_sources": [
                source.name for source in self.active_excluded_sources
            ],
            "requested_answer_shape": self.requested_answer_shape,
            "pending_clarification_field": self.pending_clarification_field,
            "previous_evidence_receipts": [
                receipt.to_dict() for receipt in self.previous_evidence_receipts
            ],
        }

    @classmethod
    def from_dict(cls, value: object) -> SessionInvestigationContext:
        if not isinstance(value, dict):
            return cls()
        incident_ids = value.get("incident_ids", ())
        raw_shape = value.get("requested_answer_shape")
        pending_field = value.get("pending_clarification_field")
        raw_receipts = value.get("previous_evidence_receipts", ())
        receipts = (
            tuple(
                receipt
                for receipt in (
                    EvidenceReceipt.from_dict(item)
                    for item in raw_receipts
                    if isinstance(raw_receipts, (list, tuple))
                )
                if receipt is not None
            )
            if isinstance(raw_receipts, (list, tuple))
            else ()
        )
        return cls(
            active_target=_optional_text(value.get("active_target")),
            active_concept=_optional_text(value.get("active_concept")),
            active_service=_optional_text(value.get("active_service")),
            active_path=_optional_text(value.get("active_path")),
            active_time_range=TimeRange.from_dict(value.get("active_time_range")),
            incident_ids=(
                tuple(str(item) for item in incident_ids if str(item))
                if isinstance(incident_ids, (list, tuple))
                else ()
            ),
            active_sources=_source_constraints(value.get("active_sources")),
            active_excluded_sources=_source_constraints(
                value.get("active_excluded_sources")
            ),
            requested_answer_shape=(
                str(raw_shape)
                if isinstance(raw_shape, str)
                and raw_shape in {"DEFAULT", "SHORT", "RAW", "EXPLAIN_PREVIOUS"}
                else "DEFAULT"
            ),
            pending_clarification_field=_optional_text(pending_field),
            previous_evidence_receipts=receipts[-_MAX_EVIDENCE_RECEIPTS:],
        )

    def update_from_frame(self, frame: RequestFrame) -> SessionInvestigationContext:
        params = frame.parameters
        service = getattr(params, "service_name", None)
        path = getattr(params, "path", None)
        incidents = tuple(
            dict.fromkeys(
                (
                    *self.incident_ids,
                    *[
                        match.upper()
                        for match in _INCIDENT_ID.findall(frame.raw_request)
                    ],
                )
            )
        )[-20:]
        concept = next(
            (item for item in frame.concepts if item != "machine"),
            self.active_concept,
        )
        return SessionInvestigationContext(
            active_target=frame.target_resolved or self.active_target,
            active_concept=concept,
            active_service=service or self.active_service,
            active_path=path or self.active_path,
            active_time_range=(
                frame.timeframe
                if isinstance(frame.timeframe, TimeRange)
                else self.active_time_range
            ),
            incident_ids=incidents,
            active_sources=(
                frame.source_constraints
                if frame.source_constraints != (SourceConstraint.ANY,)
                else self.active_sources
            ),
            active_excluded_sources=(
                frame.excluded_sources
                if frame.excluded_sources
                else self.active_excluded_sources
            ),
            requested_answer_shape=self.requested_answer_shape,
            # A successful resolution answers any pending clarification.
            pending_clarification_field=None,
            previous_evidence_receipts=self.previous_evidence_receipts,
        )

    def with_answer_shape(self, shape: str) -> SessionInvestigationContext:
        """GA2-D08: set the requested response shape (DEFAULT/SHORT/RAW/EXPLAIN_PREVIOUS)."""
        return replace(self, requested_answer_shape=shape)

    def with_pending_clarification(
        self, field: str | None
    ) -> SessionInvestigationContext:
        """GA2-E02: record which field the system just asked to clarify."""
        return replace(self, pending_clarification_field=field)

    def with_evidence_receipts(
        self, receipts: tuple[EvidenceReceipt, ...]
    ) -> SessionInvestigationContext:
        """GA2-E08: record what was actually used to answer, most-recent-last,
        capped so this never grows unboundedly across a long session."""
        if not receipts:
            return self
        combined = (*self.previous_evidence_receipts, *receipts)
        return replace(
            self, previous_evidence_receipts=combined[-_MAX_EVIDENCE_RECEIPTS:]
        )

    def with_corrected_concept(self, concept: str) -> SessionInvestigationContext:
        """GA2-D07: replace the active concept with the corrected one."""
        return replace(self, active_concept=concept)

    def switch_target(self, target: str) -> SessionInvestigationContext:
        """Switch target and clear target-scoped resource details."""
        return SessionInvestigationContext(
            active_target=target,
            incident_ids=self.incident_ids,
            active_sources=self.active_sources,
            active_excluded_sources=self.active_excluded_sources,
            requested_answer_shape=self.requested_answer_shape,
            previous_evidence_receipts=self.previous_evidence_receipts,
        )

    def reset(self) -> SessionInvestigationContext:
        return SessionInvestigationContext()


class SessionContextResolver:
    """Enrich a normalized frame before intent/target/capability planning."""

    _FOLLOW_UP = re.compile(
        r"^\s*(?:còn|con|và|va|thế còn|the con|what about|how about|and|also|same|nó|no)\b",
        re.IGNORECASE,
    )
    _REFERENCE_MARKERS = (
        "nó",
        "service đó",
        "service kia",
        "dịch vụ đó",
        "dịch vụ kia",
        "same service",
        "that service",
        "đường dẫn đó",
        "path đó",
    )
    _RESET = frozenset(
        {
            "reset context",
            "clear context",
            "xóa ngữ cảnh",
            "xoá ngữ cảnh",
            "đặt lại ngữ cảnh",
        }
    )

    # GA2-D09: ambiguous/vague referents.  They resolve only when exactly one
    # safe referent exists in session state; no implicit localhost guess.
    _VAGUE_REFERENTS = (
        "máy kia",
        "may kia",
        "server đó",
        "server do",
        "server kia",
        "cái trước",
        "cai truoc",
        "nó",
        "no",
        "that machine",
        "that server",
        "that one",
    )

    # GA2-D08: answer-shape phrases.
    _SHORT_ANSWER = (
        "ngắn thôi",
        "ngan thoi",
        "ngắn gọn",
        "ngan gon",
        "short answer",
        "keep it short",
        "briefly",
        "tóm tắt ngắn",
        "tom tat ngan",
    )
    _RAW_ANSWER = (
        "raw data only",
        "chỉ số liệu",
        "chi so lieu",
        "chỉ đưa số liệu",
        "chi dua so lieu",
        "chỉ số liệu thô",
        "chi so lieu tho",
        "no assessment",
        "không cần đánh giá",
        "khong can danh gia",
        "numbers only",
    )
    _EXPLAIN_PREVIOUS = (
        "explain that",
        "giải thích câu trước",
        "giai thich cau truoc",
        "explain the previous",
        "explain your previous answer",
        "explain previous answer",
        "explain the previous answer",
        "giải thích kỹ hơn câu trước",
        "giai thich ky hon cau truoc",
        "giải thích câu trả lời trước",
        "giai thich cau tra loi truoc",
        "explain more",
        "giải thích thêm",
        "giai thich them",
    )

    # GA2-D07: correction phrases that *replace* the active concept.
    _CORRECTION = re.compile(
        r"không\s+phải|khong\s+phai|ý\s+tôi\s+là|y\s+toi\s+la|"
        r"tôi\s+nói\s+nhầm|toi\s+noi\s+nham|nhầm\s+rồi|nham\s+roi|"
        r"i\s+meant|i\s+mean",
        re.IGNORECASE,
    )
    # GA2-D07: markers that specifically negate the concept following them
    # (as opposed to "ý tôi là"/"i meant", which instead *introduce* the
    # replacement concept). Used to tell which of two mentioned concepts is
    # being rejected so the other one can be returned as the correction.
    _NEGATION_MARKER = re.compile(
        r"không\s+phải|khong\s+phai|\bnot\b",
        re.IGNORECASE,
    )
    _CONCEPT_TOKENS = ("cpu", "ram", "memory", "disk", "network", "service")

    @classmethod
    def is_reset_request(cls, raw_request: str) -> bool:
        return raw_request.casefold().strip() in cls._RESET

    @classmethod
    def is_correction_request(cls, raw_request: str) -> bool:
        """GA2-D07: detect a correction ('Không phải CPU, RAM.')."""
        lower = raw_request.casefold()
        if not cls._CORRECTION.search(lower):
            return False
        return any(token in lower for token in cls._CONCEPT_TOKENS)

    @classmethod
    def corrected_concept(cls, raw_request: str) -> str | None:
        """GA2-D07: return the corrected (replacement) concept.

        A correction sentence names two things: the concept being rejected
        and the concept replacing it — e.g. "Không phải CPU, tôi hỏi RAM."
        rejects CPU and replaces it with RAM. The previous implementation
        scanned ``_CONCEPT_TOKENS`` in a fixed order and returned whichever
        token happened to appear first in that list, so "CPU" (checked
        first) was returned even when the sentence explicitly negated it.

        This walks every concept mention in the sentence, determines which
        one sits immediately after a negation marker (`_NEGATION_MARKER`),
        and returns the first *other* mentioned concept as the replacement.
        """
        lower = raw_request.casefold()
        token_pattern = "|".join(re.escape(token) for token in cls._CONCEPT_TOKENS)
        occurrences = [
            (match.start(), match.group(0))
            for match in re.finditer(rf"\b(?:{token_pattern})\b", lower)
        ]
        if not occurrences:
            return None
        if len(occurrences) == 1:
            return occurrences[0][1]

        negation_ends = [m.end() for m in cls._NEGATION_MARKER.finditer(lower)]
        negated_token: str | None = None
        if negation_ends:
            # The concept negated by a given marker is the *nearest*
            # concept mention that follows it (not just any later one).
            for marker_end in negation_ends:
                following = [
                    (pos, token) for pos, token in occurrences if pos >= marker_end
                ]
                if following:
                    negated_token = min(following, key=lambda item: item[0])[1]
                    break

        for _, token in occurrences:
            if token != negated_token:
                return token
        # Every mention matched the negated token (degenerate input, e.g.
        # "not CPU, not CPU"): there is no confident replacement to report.
        return None

    @classmethod
    def requested_answer_shape(cls, raw_request: str) -> str | None:
        """GA2-D08: return SHORT/RAW/EXPLAIN_PREVIOUS when confidently detected."""
        lower = raw_request.casefold()
        for shape, phrases in (
            ("SHORT", cls._SHORT_ANSWER),
            ("RAW", cls._RAW_ANSWER),
            ("EXPLAIN_PREVIOUS", cls._EXPLAIN_PREVIOUS),
        ):
            if any(phrase in lower for phrase in phrases):
                return shape
        return None

    @classmethod
    def is_vague_referent(cls, raw_request: str) -> bool:
        """GA2-D09: detect a vague referent needing a single safe resolution."""
        return any(marker in raw_request.casefold() for marker in cls._VAGUE_REFERENTS)

    @classmethod
    def is_follow_up_request(cls, raw_request: str) -> bool:
        """Return True when the request looks like a follow-up to prior state."""
        return bool(cls._FOLLOW_UP.search(raw_request.casefold()))

    def resolve(
        self,
        frame: RequestFrame,
        context: SessionInvestigationContext,
    ) -> RequestFrame:
        if context == SessionInvestigationContext():
            return frame

        raw = frame.raw_request.casefold()
        is_follow_up = bool(self._FOLLOW_UP.search(raw))
        applied: list[str] = []
        changes: dict[str, object] = {}

        # GA2-E02: a short reply directly answering a clarification question
        # the system just asked (e.g. "monitor." answering "target nào?")
        # is a follow-up even though it doesn't start with a follow-up
        # marker like "và"/"also" — it is often just the bare answer. Without
        # this, such a reply fell through every inheritance check below
        # (none of them fire without is_follow_up or high confidence), so a
        # hard source restriction established before the question was asked
        # (e.g. "Chỉ dùng Grafana...") was silently dropped/defaulted to ANY
        # on the very next turn. Guarded to short replies only (≤6 words) so
        # a genuinely new, unrelated full request right after a clarification
        # is not misread as an answer to it.
        is_pending_clarification_answer = (
            context.pending_clarification_field is not None
            and len(frame.raw_request.split()) <= 6
        )
        if is_pending_clarification_answer:
            is_follow_up = True
            if (
                context.pending_clarification_field == "target"
                and frame.target_raw is None
            ):
                answer_text = frame.raw_request.strip(" .!?\u3002")
                if answer_text:
                    changes["target_raw"] = answer_text
                    applied.append("target_from_clarification")

        # GA2-D07: a correction replaces the active concept instead of unioning.
        correction_concept = None
        if self.is_correction_request(raw):
            correction_concept = self.corrected_concept(raw)
            if correction_concept is not None:
                changes["concepts"] = (correction_concept,)
                applied.append("concept_correction")

        # GA2-D09: never inherit a target for a vague referent with no safe,
        # single referent in state; that would risk a localhost guess.
        if (
            frame.target_raw is None
            and context.active_target
            and (is_follow_up or frame.confidence >= 0.5)
            and not self.is_vague_referent(raw)
            and "target_from_clarification" not in applied
        ):
            changes["target_raw"] = context.active_target
            applied.append("target")

        if (
            is_follow_up
            and frame.source_constraints == (SourceConstraint.ANY,)
            and context.active_sources
        ):
            changes["source_constraints"] = context.active_sources
            applied.append("source")
        if (
            is_follow_up
            and not frame.excluded_sources
            and context.active_excluded_sources
        ):
            changes["excluded_sources"] = context.active_excluded_sources
            if "source" not in applied:
                applied.append("source")

        if (
            frame.concepts == ("machine",)
            and context.active_concept
            and is_follow_up
            and "concept_correction" not in applied
        ):
            changes["concepts"] = (context.active_concept,)
            applied.append("concept")

        params = frame.parameters
        if not isinstance(params, ExtractedParams):
            params = ExtractedParams()
        references_resource = is_follow_up or any(
            marker in raw for marker in self._REFERENCE_MARKERS
        )
        param_changes: dict[str, str] = {}
        if references_resource and not params.service_name and context.active_service:
            param_changes["service_name"] = context.active_service
            applied.append("service")
        if references_resource and not params.path and context.active_path:
            param_changes["path"] = context.active_path
            applied.append("path")
        if param_changes:
            changes["parameters"] = replace(params, **param_changes)

        if frame.timeframe is None and context.active_time_range and is_follow_up:
            changes["timeframe"] = context.active_time_range
            applied.append("time_range")

        if not changes:
            return frame.evolve(context_snapshot=context.to_dict())
        return frame.evolve(
            **changes,
            context_applied=tuple(applied),
            context_snapshot=context.to_dict(),
        )


def _optional_text(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _source_constraints(value: object) -> tuple[SourceConstraint, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    constraints: list[SourceConstraint] = []
    for item in value:
        try:
            constraints.append(SourceConstraint[str(item)])
        except KeyError:
            continue
    return tuple(dict.fromkeys(constraints))
