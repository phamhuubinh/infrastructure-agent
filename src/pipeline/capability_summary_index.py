"""Compact provider-neutral capability summaries for semantic selection."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.semantic_plan import (
    DeterministicComputeIntent,
    SemanticPlan,
    SemanticPlanRoute,
)

MAX_CAPABILITY_SUMMARIES = 128
MAX_CAPABILITY_PURPOSE_CHARS = 120
_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")


class CapabilitySourceFamily(str, Enum):
    NONE = "none"
    LINUX = "linux"
    GRAFANA = "grafana"
    ZABBIX = "zabbix"
    INTERNET = "internet"
    COMPUTE = "compute"


class CapabilityTargetKind(str, Enum):
    NONE = "none"
    MACHINE = "machine"
    MONITORING = "monitoring"
    EXTERNAL = "external"


class CapabilityDataKind(str, Enum):
    STABLE = "stable"
    LIVE_STATE = "live_state"
    METRIC = "metric"
    MONITORING = "monitoring"
    CURRENT_EXTERNAL = "current_external"
    DETERMINISTIC = "deterministic"


class CapabilityAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CapabilitySummary:
    """Tiny semantic record; never contains commands or parameter schemas."""

    capability_id: str
    purpose: str
    source_family: CapabilitySourceFamily
    target_kind: CapabilityTargetKind
    data_kind: CapabilityDataKind
    availability: CapabilityAvailability = CapabilityAvailability.AVAILABLE
    read_only: bool = True
    typed_arguments_required: bool = False

    def __post_init__(self) -> None:
        if not _CAPABILITY_ID.fullmatch(self.capability_id):
            raise ValueError("Capability summary ID is invalid.")
        if not self.purpose or self.purpose != self.purpose.strip():
            raise ValueError("Capability purpose must be non-empty trimmed text.")
        if len(self.purpose) > MAX_CAPABILITY_PURPOSE_CHARS:
            raise ValueError("Capability purpose exceeds the compact summary limit.")
        if any(ord(character) < 32 for character in self.purpose):
            raise ValueError("Capability purpose must not contain control characters.")
        enum_values = (
            (self.source_family, CapabilitySourceFamily, "source_family"),
            (self.target_kind, CapabilityTargetKind, "target_kind"),
            (self.data_kind, CapabilityDataKind, "data_kind"),
            (self.availability, CapabilityAvailability, "availability"),
        )
        for value, enum_type, field in enum_values:
            if not isinstance(value, enum_type):
                raise TypeError(f"{field} must be a {enum_type.__name__} value.")
        if type(self.read_only) is not bool:
            raise TypeError("read_only must be a bool.")
        if type(self.typed_arguments_required) is not bool:
            raise TypeError("typed_arguments_required must be a bool.")

    def to_prompt_dict(self) -> dict[str, str]:
        return {
            "id": self.capability_id,
            "purpose": self.purpose,
            "source": self.source_family.value,
            "target": self.target_kind.value,
            "data": self.data_kind.value,
            "availability": self.availability.value,
        }

    def to_discovery_dict(self) -> dict[str, object]:
        """Return the allowlisted summary projection for controller discovery."""

        result: dict[str, object] = {
            "capability_id": self.capability_id,
            "purpose": self.purpose,
            "source_family": self.source_family.value,
            "availability": self.availability.value,
            "read_only": self.read_only,
            "typed_arguments_required": self.typed_arguments_required,
        }
        if self.target_kind is not CapabilityTargetKind.NONE:
            result["target_kind"] = self.target_kind.value
        return result


class CapabilitySummaryIndex:
    """Immutable lookup and bounded prompt projection for capability summaries."""

    def __init__(self, summaries: Sequence[CapabilitySummary]) -> None:
        if len(summaries) > MAX_CAPABILITY_SUMMARIES:
            raise ValueError(
                f"At most {MAX_CAPABILITY_SUMMARIES} summaries are allowed."
            )
        if any(not isinstance(item, CapabilitySummary) for item in summaries):
            raise TypeError("summaries must contain CapabilitySummary values.")
        ids = [item.capability_id for item in summaries]
        if len(ids) != len(set(ids)):
            raise ValueError("Capability summary IDs must be unique.")
        self._summaries = tuple(summaries)
        self._by_id = {item.capability_id: item for item in summaries}

    @classmethod
    def default(
        cls,
        *,
        availability: Mapping[CapabilitySourceFamily, CapabilityAvailability]
        | None = None,
    ) -> CapabilitySummaryIndex:
        availability = availability or {}

        def state(family: CapabilitySourceFamily) -> CapabilityAvailability:
            return availability.get(family, CapabilityAvailability.AVAILABLE)

        return cls(
            (
                CapabilitySummary(
                    "linux.live",
                    "Inspect current Linux machine state",
                    CapabilitySourceFamily.LINUX,
                    CapabilityTargetKind.MACHINE,
                    CapabilityDataKind.LIVE_STATE,
                    state(CapabilitySourceFamily.LINUX),
                ),
                CapabilitySummary(
                    "grafana.metrics",
                    "Read monitoring metrics and dashboards",
                    CapabilitySourceFamily.GRAFANA,
                    CapabilityTargetKind.MONITORING,
                    CapabilityDataKind.METRIC,
                    state(CapabilitySourceFamily.GRAFANA),
                ),
                CapabilitySummary(
                    "zabbix.monitoring",
                    "Read monitored hosts, events, and problems",
                    CapabilitySourceFamily.ZABBIX,
                    CapabilityTargetKind.MONITORING,
                    CapabilityDataKind.MONITORING,
                    state(CapabilitySourceFamily.ZABBIX),
                ),
                CapabilitySummary(
                    "internet.current",
                    "Verify current public information",
                    CapabilitySourceFamily.INTERNET,
                    CapabilityTargetKind.EXTERNAL,
                    CapabilityDataKind.CURRENT_EXTERNAL,
                    state(CapabilitySourceFamily.INTERNET),
                ),
                CapabilitySummary(
                    "compute.deterministic",
                    "Perform exact deterministic computation",
                    CapabilitySourceFamily.COMPUTE,
                    CapabilityTargetKind.NONE,
                    CapabilityDataKind.DETERMINISTIC,
                    state(CapabilitySourceFamily.COMPUTE),
                ),
                CapabilitySummary(
                    "none.direct",
                    "Answer from stable knowledge without a tool",
                    CapabilitySourceFamily.NONE,
                    CapabilityTargetKind.NONE,
                    CapabilityDataKind.STABLE,
                    state(CapabilitySourceFamily.NONE),
                ),
            )
        )

    @property
    def summaries(self) -> tuple[CapabilitySummary, ...]:
        return self._summaries

    def get(self, capability_id: str) -> CapabilitySummary | None:
        return self._by_id.get(capability_id)

    def payload_for_plan(self, plan: SemanticPlan) -> tuple[dict[str, str], ...]:
        """Return only semantically relevant summaries for a parsed plan."""

        if not isinstance(plan, SemanticPlan):
            raise TypeError("plan must be a SemanticPlan.")
        if plan.route is not SemanticPlanRoute.CAPABILITY_ASSISTED:
            return ()
        allowed = _allowed_families(plan.source_constraints)
        excluded = _excluded_families(plan.excluded_sources)
        include_compute = (
            plan.deterministic_compute is DeterministicComputeIntent.REQUIRED
        )
        return tuple(
            summary.to_prompt_dict()
            for summary in self._summaries
            if summary.source_family is not CapabilitySourceFamily.NONE
            and (
                include_compute
                or summary.source_family is not CapabilitySourceFamily.COMPUTE
            )
            and (
                summary.source_family is CapabilitySourceFamily.COMPUTE
                or allowed is None
                or summary.source_family in allowed
            )
            and summary.source_family not in excluded
        )


def _allowed_families(
    constraints: tuple[SourceConstraint, ...],
) -> frozenset[CapabilitySourceFamily] | None:
    concrete: set[CapabilitySourceFamily] = set()
    for source in constraints:
        family = _family_for_source(source)
        if family is not None:
            concrete.add(family)
    return frozenset(concrete) if concrete else None


def _excluded_families(
    constraints: tuple[SourceConstraint, ...],
) -> frozenset[CapabilitySourceFamily]:
    excluded = {
        family
        for source in constraints
        if (family := _family_for_source(source)) is not None
    }
    if SourceConstraint.NO_INTERNET in constraints:
        excluded.add(CapabilitySourceFamily.INTERNET)
    return frozenset(excluded)


def _family_for_source(source: SourceConstraint) -> CapabilitySourceFamily | None:
    return {
        SourceConstraint.LINUX: CapabilitySourceFamily.LINUX,
        SourceConstraint.SSH: CapabilitySourceFamily.LINUX,
        SourceConstraint.GRAFANA: CapabilitySourceFamily.GRAFANA,
        SourceConstraint.ZABBIX: CapabilitySourceFamily.ZABBIX,
        SourceConstraint.INTERNET: CapabilitySourceFamily.INTERNET,
        SourceConstraint.URL_ONLY: CapabilitySourceFamily.INTERNET,
    }.get(source)


__all__ = [
    "MAX_CAPABILITY_PURPOSE_CHARS",
    "MAX_CAPABILITY_SUMMARIES",
    "CapabilityAvailability",
    "CapabilityDataKind",
    "CapabilitySourceFamily",
    "CapabilitySummary",
    "CapabilitySummaryIndex",
    "CapabilityTargetKind",
]
