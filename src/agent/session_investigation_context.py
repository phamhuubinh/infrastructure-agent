"""Small, structured semantic context for deterministic follow-up routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from src.pipeline.parameter_extractor import ExtractedParams
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.time_range_resolver import TimeRange

if TYPE_CHECKING:
    from src.pipeline.request_frame import RequestFrame


_INCIDENT_ID = re.compile(
    r"\b(?:INC|INCIDENT|PROBLEM|EVENT|ALERT)[-_:#]?\d+\b", re.IGNORECASE
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
        }

    @classmethod
    def from_dict(cls, value: object) -> SessionInvestigationContext:
        if not isinstance(value, dict):
            return cls()
        incident_ids = value.get("incident_ids", ())
        raw_shape = value.get("requested_answer_shape")
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
        )

    def with_answer_shape(self, shape: str) -> SessionInvestigationContext:
        """GA2-D08: set the requested response shape (DEFAULT/SHORT/RAW/EXPLAIN_PREVIOUS)."""
        return replace(self, requested_answer_shape=shape)

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
        "giải thích kỹ hơn câu trước",
        "giai thich ky hon cau truoc",
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
        """GA2-D07: return the corrected concept that replaces the active one."""
        lower = raw_request.casefold()
        for token in cls._CONCEPT_TOKENS:
            if token in lower:
                return token
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
