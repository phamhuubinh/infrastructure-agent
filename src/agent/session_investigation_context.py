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
        }

    @classmethod
    def from_dict(cls, value: object) -> SessionInvestigationContext:
        if not isinstance(value, dict):
            return cls()
        incident_ids = value.get("incident_ids", ())
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
        )

    def update_from_frame(self, frame: RequestFrame) -> SessionInvestigationContext:
        params = frame.parameters
        service = getattr(params, "service_name", None)
        path = getattr(params, "path", None)
        incidents = tuple(
            dict.fromkeys(
                (*self.incident_ids, *[match.upper() for match in _INCIDENT_ID.findall(frame.raw_request)])
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
        )

    def switch_target(self, target: str) -> SessionInvestigationContext:
        """Switch target and clear target-scoped resource details."""
        return SessionInvestigationContext(
            active_target=target,
            incident_ids=self.incident_ids,
            active_sources=self.active_sources,
            active_excluded_sources=self.active_excluded_sources,
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

    @classmethod
    def is_reset_request(cls, raw_request: str) -> bool:
        return raw_request.casefold().strip() in cls._RESET

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

        if (
            frame.target_raw is None
            and context.active_target
            and (is_follow_up or frame.confidence >= 0.5)
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
        if is_follow_up and not frame.excluded_sources and context.active_excluded_sources:
            changes["excluded_sources"] = context.active_excluded_sources
            if "source" not in applied:
                applied.append("source")

        if (
            frame.concepts == ("machine",)
            and context.active_concept
            and is_follow_up
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
