"""Bounded progressive disclosure over the canonical capability registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.agent.authority import ExactReferenceRegistry
from src.agent.capabilities import (
    CapabilityDefinition,
    CapabilityRegistry,
    thaw_schema,
)

MAX_DISCOVERY_SUMMARIES = 16
MAX_DISCOVERY_GROUPS = 32


class DiscoveryStatus(str, Enum):
    DISCOVERED = "discovered"
    UNKNOWN_GROUP = "unknown_group"
    EMPTY_GROUP = "empty_group"


class CapabilityDetailStatus(str, Enum):
    DISCLOSED = "disclosed"
    UNKNOWN_CAPABILITY = "unknown_capability"
    UNAVAILABLE_CAPABILITY = "unavailable_capability"


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    status: DiscoveryStatus
    group: str | None = None
    summaries: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityDetail:
    status: CapabilityDetailStatus
    capability_id: str | None = None
    detail: dict[str, object] | None = None

    @property
    def selected_capability_schema(
        self,
    ) -> dict[str, object] | None:
        if (
            self.status is not CapabilityDetailStatus.DISCLOSED
            or self.detail is None
            or self.capability_id is None
        ):
            return None

        schema = self.detail.get("arguments_schema")

        if not isinstance(schema, dict):
            return None

        return {
            "capability_id": self.capability_id,
            "arguments_schema": schema,
        }


class CapabilityDiscovery:
    """Read-only exact disclosure from the same registry used by authority."""

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        targets: ExactReferenceRegistry,
        sources: ExactReferenceRegistry,
    ) -> None:
        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError(
                "capabilities must be CapabilityRegistry."
            )
        if not isinstance(targets, ExactReferenceRegistry):
            raise TypeError(
                "targets must be ExactReferenceRegistry."
            )
        if not isinstance(sources, ExactReferenceRegistry):
            raise TypeError(
                "sources must be ExactReferenceRegistry."
            )

        self._capabilities = capabilities
        self._targets = targets
        self._sources = sources

    def groups(self) -> tuple[str, ...]:
        groups = sorted(
            {
                capability.discovery_group
                for capability in self._capabilities.capabilities
                if capability.discovery_group is not None
                and capability.available
            }
        )

        if len(groups) > MAX_DISCOVERY_GROUPS:
            raise ValueError(
                "Capability discovery group limit exceeded."
            )

        return tuple(groups)

    def discover(
        self,
        group: str,
    ) -> DiscoveryResult:
        if not isinstance(group, str) or not group:
            raise TypeError(
                "group must be a non-empty string."
            )

        known_groups = {
            capability.discovery_group
            for capability in self._capabilities.capabilities
            if capability.discovery_group is not None
        }

        if group not in known_groups:
            return DiscoveryResult(
                DiscoveryStatus.UNKNOWN_GROUP
            )

        summaries = tuple(
            self._summary(capability)
            for capability in sorted(
                self._capabilities.capabilities,
                key=lambda item: item.capability_id,
            )
            if capability.discovery_group == group
            and capability.available
        )[:MAX_DISCOVERY_SUMMARIES]

        if not summaries:
            return DiscoveryResult(
                DiscoveryStatus.EMPTY_GROUP,
                group=group,
            )

        return DiscoveryResult(
            DiscoveryStatus.DISCOVERED,
            group=group,
            summaries=summaries,
        )

    def selected_detail(
        self,
        capability_id: str,
    ) -> CapabilityDetail:
        if not isinstance(capability_id, str) or not capability_id:
            raise TypeError(
                "capability_id must be a non-empty string."
            )

        capability = self._capabilities.get(capability_id)

        if capability is None:
            return CapabilityDetail(
                CapabilityDetailStatus.UNKNOWN_CAPABILITY
            )

        if not capability.available:
            return CapabilityDetail(
                CapabilityDetailStatus.UNAVAILABLE_CAPABILITY,
                capability_id=capability_id,
            )

        return CapabilityDetail(
            CapabilityDetailStatus.DISCLOSED,
            capability_id=capability_id,
            detail=self._detail(capability),
        )

    def _summary(
        self,
        capability: CapabilityDefinition,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "capability_id": capability.capability_id,
            "purpose": capability.purpose,
            "tool_id": capability.tool_id,
            "effect": capability.effect.value,
            "result_kind": capability.result_kind,
        }

        if capability.target_kind is not None:
            result["target_kind"] = capability.target_kind

        if capability.source_kind is not None:
            result["source_kind"] = capability.source_kind

        if capability.activity_label is not None:
            result["activity_label"] = capability.activity_label

        return result

    def _detail(
        self,
        capability: CapabilityDefinition,
    ) -> dict[str, object]:
        detail = self._summary(capability)

        detail["arguments_schema"] = thaw_schema(
            capability.arguments_schema
        )
        detail["budget_cost"] = capability.budget_cost
        detail["target_refs"] = list(
            self._allowed_refs(
                capability.target_kind,
                capability.allowed_target_refs,
                self._targets,
            )
        )
        detail["source_refs"] = list(
            self._allowed_refs(
                capability.source_kind,
                capability.allowed_source_refs,
                self._sources,
            )
        )

        return detail

    @staticmethod
    def _allowed_refs(
        required_kind: str | None,
        allowed_refs: frozenset[str] | None,
        registry: ExactReferenceRegistry,
    ) -> tuple[str, ...]:
        if required_kind is None:
            return ()

        refs = {
            entry.ref_id
            for entry in registry.entries
            if entry.kind == required_kind
            and entry.available
        }

        if allowed_refs is not None:
            refs.intersection_update(allowed_refs)

        return tuple(sorted(refs))


__all__ = [
    "CapabilityDetail",
    "CapabilityDetailStatus",
    "CapabilityDiscovery",
    "DiscoveryResult",
    "DiscoveryStatus",
]
