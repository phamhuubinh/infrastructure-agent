"""Bounded, metadata-only capability discovery for the Agent v2 controller.

This module deliberately projects existing ``KnowledgeTool`` declarations.  It
does not own a registry, select alternatives, invoke collectors, or construct
an execution request.  The returned records are suitable only for the
controller's next advisory decision.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from src.pipeline.calculator_action_contract import (
    CALCULATOR_CAPABILITY_ID,
    calculator_arguments_schema,
)
from src.pipeline.capability_summary_index import (
    CapabilityAvailability,
    CapabilityDataKind,
    CapabilitySourceFamily,
    CapabilitySummary,
    CapabilitySummaryIndex,
    CapabilityTargetKind,
)
from src.pipeline.hard_request_constraints import HardRequestConstraints
from src.pipeline.internet_action_contract import (
    INTERNET_CURRENT_CAPABILITY_ID,
    INTERNET_FETCH_URL_CAPABILITY_ID,
    internet_current_arguments_schema,
    internet_fetch_url_arguments_schema,
)
from src.pipeline.request_semantics import SourceConstraint
from src.tool.knowledge_tool import KnowledgeTool

CONTROLLER_CAPABILITY_CATEGORIES = (
    "host",
    "grafana",
    "zabbix",
    "internet",
    "calculator",
)
MAX_DISCOVERY_SUMMARIES_PER_CATEGORY = 16
MAX_DISCOVERY_PAYLOAD_BYTES = 4_096
MAX_SELECTED_CAPABILITY_DETAIL_BYTES = 2_048
MAX_DISCOVERY_ARGUMENTS = 16

# Keep the bounded host disclosure useful for controller-selected Linux
# investigations.  This is ordering only: every ID still originates from the
# current KnowledgeTool metadata and all non-prioritized host metadata follows
# in stable capability-ID order.
_HOST_DISCOVERY_PRIORITY = (
    "host.get_cpu",
    "host.get_memory",
    "host.get_filesystem",
    "host.get_process",
    "host.get_service",
    "host.get_network",
    "host.get_system",
    "host.get_uptime",
)
_HOST_DISCOVERY_PRIORITY_RANK = {
    capability_id: rank for rank, capability_id in enumerate(_HOST_DISCOVERY_PRIORITY)
}


class CapabilityDiscoveryStatus(str, Enum):
    DISCOVERED = "discovered"
    UNKNOWN_CATEGORY = "unknown_category"
    UNAVAILABLE_CATEGORY = "unavailable_category"


class CapabilityDetailStatus(str, Enum):
    DISCLOSED = "disclosed"
    UNKNOWN_CAPABILITY = "unknown_capability"
    UNAVAILABLE_CAPABILITY = "unavailable_capability"


@dataclass(frozen=True, slots=True)
class CapabilityDiscoveryResult:
    """Small typed result for one category-only discovery request."""

    status: CapabilityDiscoveryStatus
    category: str | None = None
    summaries: tuple[dict[str, object], ...] = ()

    def to_payload(self) -> dict[str, object]:
        if self.status is CapabilityDiscoveryStatus.UNKNOWN_CATEGORY:
            return {"status": self.status.value}
        payload: dict[str, object] = {
            "status": self.status.value,
            "category": self.category,
        }
        if self.status is CapabilityDiscoveryStatus.DISCOVERED:
            payload["summaries"] = list(self.summaries)
        return payload


@dataclass(frozen=True, slots=True)
class SelectedCapabilityDetailResult:
    """Small typed result for an exact selected capability ID lookup."""

    status: CapabilityDetailStatus
    capability_id: str | None = None
    selected_capability_schema: dict[str, object] | None = None
    source_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        if self.status is CapabilityDetailStatus.UNKNOWN_CAPABILITY:
            return {"status": self.status.value}
        payload: dict[str, object] = {
            "status": self.status.value,
            "capability_id": self.capability_id,
        }
        if self.status is CapabilityDetailStatus.DISCLOSED:
            payload["selected_capability_schema"] = self.selected_capability_schema
        return payload


@dataclass(frozen=True, slots=True)
class _Detail:
    category: str
    summary: CapabilitySummary
    arguments_schema: dict[str, object]
    source_ids: tuple[str, ...] = ()


class ControllerCapabilityDiscovery:
    """Project the existing metadata/index layer for bounded controller use."""

    def __init__(self, details: Sequence[_Detail]) -> None:
        if any(not isinstance(detail, _Detail) for detail in details):
            raise TypeError("details must contain _Detail values.")
        ids = [detail.summary.capability_id for detail in details]
        if len(ids) != len(set(ids)):
            raise ValueError("Controller capability IDs must be unique.")
        self._index = CapabilitySummaryIndex(
            tuple(detail.summary for detail in details)
        )
        self._details = {detail.summary.capability_id: detail for detail in details}
        self._by_category = {
            category: tuple(
                sorted(
                    (
                        detail
                        for detail in details
                        if detail.category == category
                        and detail.summary.availability
                        is CapabilityAvailability.AVAILABLE
                    ),
                    key=lambda detail: _discovery_order_key(category, detail),
                )
            )
            for category in CONTROLLER_CAPABILITY_CATEGORIES
        }

    @classmethod
    def from_knowledge_tool(
        cls, knowledge_tool: KnowledgeTool
    ) -> ControllerCapabilityDiscovery:
        """Build a read-only projection from ``KnowledgeTool`` metadata only."""

        if not isinstance(knowledge_tool, KnowledgeTool):
            raise TypeError("knowledge_tool must be a KnowledgeTool.")
        details_by_id: dict[str, _Detail] = {}
        internet_resources: dict[str, set[str]] = {}
        metadata = knowledge_tool.get_capability_metadata()
        for source in sorted(metadata):
            category = _category_for_source_kind(knowledge_tool.source_kind(source))
            if category is None:
                continue
            if category == "internet":
                internet_resources[source] = {
                    name
                    for entry in metadata[source]
                    if isinstance((name := entry.get("name")), str)
                }
                continue
            for entry in sorted(metadata[source], key=_metadata_name):
                detail = _detail_from_metadata(category, entry)
                if detail is None:
                    continue
                capability_id = detail.summary.capability_id
                existing = details_by_id.get(capability_id)
                if existing is None:
                    details_by_id[capability_id] = replace(detail, source_ids=(source,))
                elif source not in existing.source_ids:
                    details_by_id[capability_id] = replace(
                        existing, source_ids=existing.source_ids + (source,)
                    )
        details = list(details_by_id.values())
        details.extend(_internet_action_details(internet_resources))
        details.append(_calculator_detail())
        configured_categories = {detail.category for detail in details}
        details.extend(_unavailable_category_details(configured_categories))
        return cls(details)

    def discover(
        self,
        category: str,
        hard_constraints: HardRequestConstraints,
    ) -> CapabilityDiscoveryResult:
        """Return only bounded summaries for one exact category, never execute."""

        if not isinstance(category, str):
            raise TypeError("category must be a string.")
        if not isinstance(hard_constraints, HardRequestConstraints):
            raise TypeError("hard_constraints must be HardRequestConstraints.")
        if category not in CONTROLLER_CAPABILITY_CATEGORIES:
            return CapabilityDiscoveryResult(CapabilityDiscoveryStatus.UNKNOWN_CATEGORY)
        allowed = _allowed_categories(hard_constraints)
        if allowed is not None and category not in allowed and category != "calculator":
            return CapabilityDiscoveryResult(
                CapabilityDiscoveryStatus.UNAVAILABLE_CATEGORY, category
            )
        summaries = tuple(
            detail.summary.to_discovery_dict()
            for detail in self._by_category[category]
            if _summary_allowed(detail.summary, hard_constraints)
        )[:MAX_DISCOVERY_SUMMARIES_PER_CATEGORY]
        if not summaries:
            return CapabilityDiscoveryResult(
                CapabilityDiscoveryStatus.UNAVAILABLE_CATEGORY, category
            )
        result = CapabilityDiscoveryResult(
            CapabilityDiscoveryStatus.DISCOVERED, category, summaries
        )
        _ensure_payload_limit(result.to_payload(), MAX_DISCOVERY_PAYLOAD_BYTES)
        return result

    def selected_detail(
        self,
        capability_id: str,
        hard_constraints: HardRequestConstraints,
    ) -> SelectedCapabilityDetailResult:
        """Resolve one exact ID only; constraints filter but never substitute."""

        if not isinstance(capability_id, str):
            raise TypeError("capability_id must be a string.")
        if not isinstance(hard_constraints, HardRequestConstraints):
            raise TypeError("hard_constraints must be HardRequestConstraints.")
        detail = self._details.get(capability_id)
        if detail is None:
            return SelectedCapabilityDetailResult(
                CapabilityDetailStatus.UNKNOWN_CAPABILITY
            )
        if (
            detail.summary.availability is CapabilityAvailability.UNAVAILABLE
            or not _summary_allowed(detail.summary, hard_constraints)
        ):
            return SelectedCapabilityDetailResult(
                CapabilityDetailStatus.UNAVAILABLE_CAPABILITY, capability_id
            )
        selected_schema = {
            "capability_id": capability_id,
            "arguments_schema": detail.arguments_schema,
            "target_requirements": _target_requirements(detail.summary),
            "source_requirements": _source_requirements(detail.summary),
            "usage": detail.summary.purpose,
            "availability": detail.summary.availability.value,
            "read_only": detail.summary.read_only,
        }
        _ensure_payload_limit(selected_schema, MAX_SELECTED_CAPABILITY_DETAIL_BYTES)
        return SelectedCapabilityDetailResult(
            CapabilityDetailStatus.DISCLOSED,
            capability_id,
            selected_schema,
            detail.source_ids,
        )


def _detail_from_metadata(category: str, entry: Mapping[str, object]) -> _Detail | None:
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    capability_id = f"{category}.{name}"
    purpose = entry.get("description")
    if not isinstance(purpose, str) or not purpose.strip():
        purpose = f"Read {name.replace('_', ' ')} information"
    purpose = purpose.strip()[:120]
    source_family, target_kind, data_kind = _category_metadata(category)
    mutation_risk = entry.get("mutation_risk")
    summary = CapabilitySummary(
        capability_id=capability_id,
        purpose=purpose,
        source_family=source_family,
        target_kind=target_kind,
        data_kind=data_kind,
        read_only=mutation_risk == "none",
        typed_arguments_required=any(
            isinstance(spec, Mapping) and spec.get("required") is True
            for spec in _metadata_sequence(entry.get("parameter_specs"))
        ),
    )
    return _Detail(category, summary, _arguments_schema(entry))


def _calculator_detail() -> _Detail:
    """Return the deterministic calculator without inventing a tool source."""

    summary = next(
        item
        for item in CapabilitySummaryIndex.default().summaries
        if item.capability_id == CALCULATOR_CAPABILITY_ID
    )
    return _Detail(
        "calculator",
        replace(summary, typed_arguments_required=True),
        calculator_arguments_schema(),
    )


def _internet_action_details(resources: Mapping[str, set[str]]) -> tuple[_Detail, ...]:
    """Project reviewed actions, never the InternetTool primitives themselves."""

    default = CapabilitySummaryIndex.default()
    current = next(
        summary
        for summary in default.summaries
        if summary.capability_id == INTERNET_CURRENT_CAPABILITY_ID
    )
    fetch = next(
        summary
        for summary in default.summaries
        if summary.capability_id == INTERNET_FETCH_URL_CAPABILITY_ID
    )
    fetch_sources = tuple(
        source for source, names in sorted(resources.items()) if "web_fetch" in names
    )
    current_sources = tuple(
        source
        for source, names in sorted(resources.items())
        if {"web_search", "web_fetch"}.issubset(names)
    )
    return (
        _Detail(
            "internet",
            replace(
                current,
                availability=(
                    CapabilityAvailability.AVAILABLE
                    if current_sources
                    else CapabilityAvailability.UNAVAILABLE
                ),
                typed_arguments_required=True,
            ),
            internet_current_arguments_schema(),
            current_sources,
        ),
        _Detail(
            "internet",
            replace(
                fetch,
                availability=(
                    CapabilityAvailability.AVAILABLE
                    if fetch_sources
                    else CapabilityAvailability.UNAVAILABLE
                ),
                typed_arguments_required=True,
            ),
            internet_fetch_url_arguments_schema(),
            fetch_sources,
        ),
    )


def _unavailable_category_details(
    configured_categories: set[str],
) -> tuple[_Detail, ...]:
    """Retain known coarse IDs for stable unavailable-selection results.

    These records reuse the existing compact index defaults.  They add no
    execution metadata and are excluded from discovery, which still reports
    an unavailable category rather than a misleading empty capability list.
    """

    category_by_family = {
        CapabilitySourceFamily.LINUX: "host",
        CapabilitySourceFamily.GRAFANA: "grafana",
        CapabilitySourceFamily.ZABBIX: "zabbix",
        CapabilitySourceFamily.INTERNET: "internet",
        CapabilitySourceFamily.COMPUTE: "calculator",
    }
    details: list[_Detail] = []
    for summary in CapabilitySummaryIndex.default().summaries:
        category = category_by_family.get(summary.source_family)
        if category is None or category in configured_categories:
            continue
        unavailable = CapabilitySummary(
            capability_id=summary.capability_id,
            purpose=summary.purpose,
            source_family=summary.source_family,
            target_kind=summary.target_kind,
            data_kind=summary.data_kind,
            availability=CapabilityAvailability.UNAVAILABLE,
            read_only=summary.read_only,
            typed_arguments_required=summary.typed_arguments_required,
        )
        details.append(
            _Detail(
                category,
                unavailable,
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {},
                    "required": [],
                },
            )
        )
    return tuple(details)


def _arguments_schema(entry: Mapping[str, object]) -> dict[str, object]:
    specs = {
        spec["name"]: spec
        for spec in _metadata_sequence(entry.get("parameter_specs"))
        if isinstance(spec, Mapping) and isinstance(spec.get("name"), str)
    }
    names = {
        name
        for name in _metadata_sequence(entry.get("parameters"))
        if isinstance(name, str) and name not in {"action", "resource", "source"}
    }
    names.update(name for name in specs if name not in {"action", "resource", "source"})
    if len(names) > MAX_DISCOVERY_ARGUMENTS:
        raise ValueError("Capability arguments exceed the controller disclosure limit.")
    properties = {name: _property_schema(specs.get(name)) for name in sorted(names)}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _property_schema(spec: Mapping[str, object] | None) -> dict[str, object]:
    value_type = spec.get("value_type") if spec is not None else "str"
    if not isinstance(value_type, str):
        value_type = "str"
    json_type = {
        "str": "string",
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "number": "number",
        "bool": "boolean",
        "boolean": "boolean",
    }.get(value_type, "string")
    optional = spec is None or spec.get("required") is not True
    result: dict[str, object] = {
        "type": [json_type, "null"] if optional else json_type,
    }
    if spec is None:
        return result
    enum = spec.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes)) and enum:
        values = list(enum)
        if optional and None not in values:
            values.append(None)
        result["enum"] = values
    if json_type in {"integer", "number"}:
        for source_key, schema_key in (("minimum", "minimum"), ("maximum", "maximum")):
            bound = spec.get(source_key)
            if isinstance(bound, (int, float)) and not isinstance(bound, bool):
                result[schema_key] = bound
    pattern = spec.get("pattern")
    if isinstance(pattern, str) and pattern:
        result["pattern"] = pattern
    return result


def _metadata_sequence(value: object) -> Sequence[object]:
    return (
        value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        else ()
    )


def _metadata_name(entry: Mapping[str, object]) -> str:
    name = entry.get("name")
    return name if isinstance(name, str) else ""


def _discovery_order_key(category: str, detail: _Detail) -> tuple[int, int | str]:
    """Return the category-local, metadata-independent disclosure order."""

    capability_id = detail.summary.capability_id
    if category == "host":
        priority = _HOST_DISCOVERY_PRIORITY_RANK.get(capability_id)
        if priority is not None:
            return (0, priority)
    return (1, capability_id)


def _category_for_source_kind(source_kind: str) -> str | None:
    return {
        "linux": "host",
        "grafana": "grafana",
        "zabbix": "zabbix",
        "internet": "internet",
    }.get(source_kind)


def _category_metadata(
    category: str,
) -> tuple[CapabilitySourceFamily, CapabilityTargetKind, CapabilityDataKind]:
    return {
        "host": (
            CapabilitySourceFamily.LINUX,
            CapabilityTargetKind.MACHINE,
            CapabilityDataKind.LIVE_STATE,
        ),
        "grafana": (
            CapabilitySourceFamily.GRAFANA,
            CapabilityTargetKind.MONITORING,
            CapabilityDataKind.METRIC,
        ),
        "zabbix": (
            CapabilitySourceFamily.ZABBIX,
            CapabilityTargetKind.MONITORING,
            CapabilityDataKind.MONITORING,
        ),
        "internet": (
            CapabilitySourceFamily.INTERNET,
            CapabilityTargetKind.EXTERNAL,
            CapabilityDataKind.CURRENT_EXTERNAL,
        ),
    }[category]


def _allowed_categories(constraints: HardRequestConstraints) -> frozenset[str] | None:
    allowed = {
        category
        for source in constraints.source_constraints
        if (category := _category_for_constraint(source)) is not None
    }
    return frozenset(allowed) if allowed else None


def _summary_allowed(
    summary: CapabilitySummary, constraints: HardRequestConstraints
) -> bool:
    if summary.source_family is CapabilitySourceFamily.COMPUTE:
        return True
    category = _category_for_family(summary.source_family)
    allowed = _allowed_categories(constraints)
    if allowed is not None and category not in allowed:
        return False
    excluded = {
        _category_for_constraint(source) for source in constraints.excluded_sources
    }
    if SourceConstraint.NO_INTERNET in constraints.source_constraints:
        excluded.add("internet")
    return category not in excluded


def _category_for_constraint(source: SourceConstraint) -> str | None:
    return {
        SourceConstraint.LINUX: "host",
        SourceConstraint.SSH: "host",
        SourceConstraint.GRAFANA: "grafana",
        SourceConstraint.ZABBIX: "zabbix",
        SourceConstraint.INTERNET: "internet",
        SourceConstraint.URL_ONLY: "internet",
    }.get(source)


def _category_for_family(family: CapabilitySourceFamily) -> str:
    return {
        CapabilitySourceFamily.LINUX: "host",
        CapabilitySourceFamily.GRAFANA: "grafana",
        CapabilitySourceFamily.ZABBIX: "zabbix",
        CapabilitySourceFamily.INTERNET: "internet",
        CapabilitySourceFamily.COMPUTE: "calculator",
    }[family]


def _target_requirements(summary: CapabilitySummary) -> dict[str, object]:
    return {
        "kind": summary.target_kind.value,
        # Only Linux-style machine capabilities consume a target-registry
        # machine identity.  Grafana/Zabbix are source-backed capabilities;
        # requiring a model-selected machine target here would incorrectly
        # authorize an unrelated host as their monitoring source.
        "required": summary.target_kind is CapabilityTargetKind.MACHINE,
    }


def _source_requirements(summary: CapabilitySummary) -> dict[str, object]:
    return {
        "family": summary.source_family.value,
        "required": summary.source_family is not CapabilitySourceFamily.COMPUTE,
    }


def _ensure_payload_limit(value: Mapping[str, object], maximum: int) -> None:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    if len(encoded.encode("utf-8")) > maximum:
        raise ValueError("Capability disclosure exceeds its deterministic byte limit.")


__all__ = [
    "CONTROLLER_CAPABILITY_CATEGORIES",
    "MAX_DISCOVERY_ARGUMENTS",
    "MAX_DISCOVERY_PAYLOAD_BYTES",
    "MAX_DISCOVERY_SUMMARIES_PER_CATEGORY",
    "MAX_SELECTED_CAPABILITY_DETAIL_BYTES",
    "CapabilityDetailStatus",
    "CapabilityDiscoveryResult",
    "CapabilityDiscoveryStatus",
    "ControllerCapabilityDiscovery",
    "SelectedCapabilityDetailResult",
]
