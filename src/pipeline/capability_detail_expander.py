"""Lazy, single-selection expansion of existing capability references."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_summary_index import (
    CapabilityAvailability,
    CapabilitySourceFamily,
    CapabilitySummary,
    CapabilitySummaryIndex,
)
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.semantic_plan import SemanticPlanRoute
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationResult,
    SemanticPlanValidationStatus,
)


class CapabilityExpansionStatus(str, Enum):
    EXPANDED = "expanded"
    UNAVAILABLE = "unavailable"
    NOT_FOUND = "not_found"
    PLAN_NOT_VALID = "plan_not_valid"
    SOURCE_BLOCKED = "source_blocked"


class CapabilityExpansionReason(str, Enum):
    DETAIL_EXPANDED = "detail_expanded"
    PLAN_NOT_VALIDATED = "plan_not_validated"
    PLAN_DOES_NOT_SELECT_CAPABILITY = "plan_does_not_select_capability"
    CAPABILITY_ID_UNKNOWN = "capability_id_unknown"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CAPABILITY_DETAIL_MISSING = "capability_detail_missing"
    SOURCE_NOT_ALLOWED = "source_not_allowed"


@dataclass(frozen=True, slots=True)
class CapabilityExpansionResult:
    status: CapabilityExpansionStatus
    reason: CapabilityExpansionReason
    selected_capability_id: str
    summary: CapabilitySummary | None = None
    capability: CapabilityReference | None = None

    @property
    def expanded(self) -> bool:
        return self.status is CapabilityExpansionStatus.EXPANDED

    def to_trace_dict(self) -> dict[str, object]:
        trace: dict[str, object] = {
            "status": self.status.value,
            "reason": self.reason.value,
            "selected_capability_id": self.selected_capability_id,
            "expanded": self.expanded,
        }
        if self.summary is not None:
            trace["source_family"] = self.summary.source_family.value
        return trace


class LazyCapabilityDetailExpander:
    """Expand exactly one selected ID; never searches for an alternative."""

    def __init__(
        self,
        index: CapabilitySummaryIndex,
        details: Mapping[str, CapabilityReference],
    ) -> None:
        if not isinstance(index, CapabilitySummaryIndex):
            raise TypeError("index must be a CapabilitySummaryIndex.")
        if any(not isinstance(key, str) for key in details):
            raise TypeError("Capability detail IDs must be strings.")
        if any(
            not isinstance(value, CapabilityReference) for value in details.values()
        ):
            raise TypeError("Capability details must be CapabilityReference values.")
        self._index = index
        self._details = dict(details)

    def expand(
        self,
        selected_capability_id: str,
        validation: SemanticPlanValidationResult,
    ) -> CapabilityExpansionResult:
        if not isinstance(selected_capability_id, str):
            raise TypeError("selected_capability_id must be a string.")
        if not isinstance(validation, SemanticPlanValidationResult):
            raise TypeError("validation must be SemanticPlanValidationResult.")
        if validation.status is not SemanticPlanValidationStatus.VALID:
            return _result(
                selected_capability_id,
                CapabilityExpansionStatus.PLAN_NOT_VALID,
                CapabilityExpansionReason.PLAN_NOT_VALIDATED,
            )
        plan = validation.validated_plan
        if plan is None or plan.route is not SemanticPlanRoute.CAPABILITY_ASSISTED:
            return _result(
                selected_capability_id,
                CapabilityExpansionStatus.PLAN_NOT_VALID,
                CapabilityExpansionReason.PLAN_DOES_NOT_SELECT_CAPABILITY,
            )

        summary = self._index.get(selected_capability_id)
        if summary is None:
            return _result(
                selected_capability_id,
                CapabilityExpansionStatus.NOT_FOUND,
                CapabilityExpansionReason.CAPABILITY_ID_UNKNOWN,
            )
        if summary.availability is CapabilityAvailability.UNAVAILABLE:
            return _result(
                selected_capability_id,
                CapabilityExpansionStatus.UNAVAILABLE,
                CapabilityExpansionReason.CAPABILITY_UNAVAILABLE,
                summary,
            )
        if not _source_allowed(
            summary.source_family,
            plan.source_constraints,
            plan.excluded_sources,
        ):
            return _result(
                selected_capability_id,
                CapabilityExpansionStatus.SOURCE_BLOCKED,
                CapabilityExpansionReason.SOURCE_NOT_ALLOWED,
                summary,
            )

        capability = self._details.get(selected_capability_id)
        if capability is None:
            return _result(
                selected_capability_id,
                CapabilityExpansionStatus.UNAVAILABLE,
                CapabilityExpansionReason.CAPABILITY_DETAIL_MISSING,
                summary,
            )
        return CapabilityExpansionResult(
            status=CapabilityExpansionStatus.EXPANDED,
            reason=CapabilityExpansionReason.DETAIL_EXPANDED,
            selected_capability_id=selected_capability_id,
            summary=summary,
            capability=capability,
        )


def _result(
    selected_capability_id: str,
    status: CapabilityExpansionStatus,
    reason: CapabilityExpansionReason,
    summary: CapabilitySummary | None = None,
) -> CapabilityExpansionResult:
    return CapabilityExpansionResult(
        status=status,
        reason=reason,
        selected_capability_id=selected_capability_id,
        summary=summary,
    )


def _source_allowed(
    family: CapabilitySourceFamily,
    allowed: tuple[SourceConstraint, ...],
    excluded: tuple[SourceConstraint, ...],
) -> bool:
    if family in {CapabilitySourceFamily.NONE, CapabilitySourceFamily.COMPUTE}:
        return True
    source_families = {
        source_family
        for source in allowed
        if (source_family := _source_family(source)) is not None
    }
    excluded_families = {
        source_family
        for source in excluded
        if (source_family := _source_family(source)) is not None
    }
    if SourceConstraint.NO_INTERNET in allowed:
        excluded_families.add(CapabilitySourceFamily.INTERNET)
    if family in excluded_families:
        return False
    return not source_families or family in source_families


def _source_family(source: SourceConstraint) -> CapabilitySourceFamily | None:
    return {
        SourceConstraint.LINUX: CapabilitySourceFamily.LINUX,
        SourceConstraint.SSH: CapabilitySourceFamily.LINUX,
        SourceConstraint.GRAFANA: CapabilitySourceFamily.GRAFANA,
        SourceConstraint.ZABBIX: CapabilitySourceFamily.ZABBIX,
        SourceConstraint.INTERNET: CapabilitySourceFamily.INTERNET,
        SourceConstraint.URL_ONLY: CapabilitySourceFamily.INTERNET,
    }.get(source)


__all__ = [
    "CapabilityExpansionReason",
    "CapabilityExpansionResult",
    "CapabilityExpansionStatus",
    "LazyCapabilityDetailExpander",
]
