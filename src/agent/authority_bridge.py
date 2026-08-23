"""Compatibility bridge from current tool metadata to canonical authority.

This module exists only during migration. It reads registered metadata and
constructs the new exact authority catalogs. It performs no language parsing,
fuzzy resolution, capability selection, or execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from src.agent.authority import (
    ExactReferenceRegistry,
    ReferenceEntry,
)
from src.agent.capabilities import (
    CapabilityDefinition,
    CapabilityRegistry,
)
from src.agent.permissions import EffectClass
from src.pipeline.calculator_action_contract import (
    CALCULATOR_CAPABILITY_ID,
    calculator_arguments_schema,
)
from src.pipeline.internet_action_contract import (
    INTERNET_CURRENT_CAPABILITY_ID,
    INTERNET_FETCH_URL_CAPABILITY_ID,
    internet_current_arguments_schema,
    internet_fetch_url_arguments_schema,
)
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


@dataclass(frozen=True, slots=True)
class AuthorityCatalog:
    capabilities: CapabilityRegistry
    targets: ExactReferenceRegistry
    sources: ExactReferenceRegistry


@dataclass(slots=True)
class _LegacyCapability:
    capability_id: str
    purpose: str
    tool_id: str
    effect: EffectClass
    arguments_schema: dict[str, object]
    runtime_binding: str
    discovery_group: str
    target_kind: str | None
    source_kind: str | None
    allowed_target_refs: set[str]
    allowed_source_refs: set[str]


def build_legacy_authority_catalog(
    knowledge_tool: KnowledgeTool,
    target_registry: TargetRegistry,
) -> AuthorityCatalog:
    """Project current reviewed registrations into the new authority model."""

    if not isinstance(knowledge_tool, KnowledgeTool):
        raise TypeError("knowledge_tool must be KnowledgeTool.")

    if not isinstance(target_registry, TargetRegistry):
        raise TypeError("target_registry must be TargetRegistry.")

    registry_names = tuple(target_registry.target_names())
    knowledge_names = tuple(sorted(knowledge_tool.source_names()))

    if tuple(sorted(registry_names)) != knowledge_names:
        raise ValueError(
            "knowledge_tool and target_registry must describe "
            "the same registrations."
        )

    targets = ExactReferenceRegistry(
        tuple(
            ReferenceEntry(name, "machine")
            for name in registry_names
            if target_registry.backend(name) is not None
        )
    )

    sources = ExactReferenceRegistry(
        tuple(
            ReferenceEntry(
                name,
                knowledge_tool.source_kind(name),
            )
            for name in target_registry.domain_tool_names()
        )
    )

    metadata = knowledge_tool.get_capability_metadata()
    accumulated: dict[str, _LegacyCapability] = {}
    internet_resources: dict[str, set[str]] = {}

    for source_ref in sorted(metadata):
        entries = metadata[source_ref]
        source_kind = knowledge_tool.source_kind(source_ref)

        if source_kind == "internet":
            internet_resources[source_ref] = {
                name
                for entry in entries
                if isinstance((name := entry.get("name")), str)
                and name
            }
            continue

        for entry in entries:
            _accumulate_metadata_capability(
                accumulated,
                source_ref=source_ref,
                source_kind=source_kind,
                entry=entry,
            )

    capabilities = [
        _finalize_legacy_capability(item)
        for _, item in sorted(accumulated.items())
    ]

    capabilities.extend(
        _internet_capabilities(internet_resources)
    )
    capabilities.append(_calculator_capability())

    return AuthorityCatalog(
        capabilities=CapabilityRegistry(tuple(capabilities)),
        targets=targets,
        sources=sources,
    )


def _accumulate_metadata_capability(
    accumulated: dict[str, _LegacyCapability],
    *,
    source_ref: str,
    source_kind: str,
    entry: Mapping[str, object],
) -> None:
    name = entry.get("name")
    mutation_risk = entry.get("mutation_risk")

    # Entries without reviewed capability metadata are not authority.
    if (
        not isinstance(name, str)
        or not name
        or mutation_risk not in {"none", "low", "medium", "high"}
    ):
        return

    prefix = "host" if source_kind == "linux" else source_kind
    capability_id = f"{prefix}.{name}"
    effect = (
        EffectClass.READ
        if mutation_risk == "none"
        else EffectClass.WRITE
    )

    description = entry.get("description")
    purpose = (
        description.strip()
        if isinstance(description, str) and description.strip()
        else f"Use {name.replace('_', ' ')}"
    )
    purpose = purpose[:1024].strip()

    target_kind = "machine" if source_kind == "linux" else None
    capability_source_kind = (
        None
        if source_kind == "linux"
        else source_kind
    )

    candidate = _LegacyCapability(
        capability_id=capability_id,
        purpose=purpose,
        tool_id=source_kind,
        effect=effect,
        arguments_schema=_arguments_schema(entry),
        runtime_binding="knowledge.dispatch",
        discovery_group=(
            "host"
            if source_kind == "linux"
            else source_kind
        ),
        target_kind=target_kind,
        source_kind=capability_source_kind,
        allowed_target_refs=(
            {source_ref}
            if target_kind is not None
            else set()
        ),
        allowed_source_refs=(
            {source_ref}
            if capability_source_kind is not None
            else set()
        ),
    )

    existing = accumulated.get(capability_id)

    if existing is None:
        accumulated[capability_id] = candidate
        return

    if not _same_authority_shape(existing, candidate):
        raise ValueError(
            f"Conflicting metadata for capability {capability_id!r}."
        )

    existing.allowed_target_refs.update(
        candidate.allowed_target_refs
    )
    existing.allowed_source_refs.update(
        candidate.allowed_source_refs
    )


def _same_authority_shape(
    left: _LegacyCapability,
    right: _LegacyCapability,
) -> bool:
    return (
        left.capability_id == right.capability_id
        and left.purpose == right.purpose
        and left.tool_id == right.tool_id
        and left.effect is right.effect
        and left.arguments_schema == right.arguments_schema
        and left.runtime_binding == right.runtime_binding
        and left.discovery_group == right.discovery_group
        and left.target_kind == right.target_kind
        and left.source_kind == right.source_kind
    )


def _finalize_legacy_capability(
    item: _LegacyCapability,
) -> CapabilityDefinition:
    # Legacy WRITE metadata is classified, but not executable until Phase 7
    # explicitly reviews and enables that capability.
    write = item.effect is EffectClass.WRITE

    return CapabilityDefinition(
        capability_id=item.capability_id,
        purpose=item.purpose,
        tool_id=item.tool_id,
        effect=item.effect,
        arguments_schema=item.arguments_schema,
        runtime_binding=item.runtime_binding,
        discovery_group=item.discovery_group,
        target_kind=item.target_kind,
        source_kind=item.source_kind,
        allowed_target_refs=(
            frozenset(item.allowed_target_refs)
            if item.target_kind is not None
            else None
        ),
        allowed_source_refs=(
            frozenset(item.allowed_source_refs)
            if item.source_kind is not None
            else None
        ),
        available=not write,
        safety_reviewed=not write,
        budget_cost=1,
        result_kind="observation",
        activity_label=item.purpose,
    )


def _internet_capabilities(
    resources: Mapping[str, set[str]],
) -> tuple[CapabilityDefinition, ...]:
    if not resources:
        return ()

    fetch_sources = frozenset(
        source
        for source, names in resources.items()
        if "web_fetch" in names
    )
    current_sources = frozenset(
        source
        for source, names in resources.items()
        if {"web_search", "web_fetch"}.issubset(names)
    )

    return (
        CapabilityDefinition(
            capability_id=INTERNET_CURRENT_CAPABILITY_ID,
            purpose="Verify current public information",
            tool_id="internet",
            effect=EffectClass.READ,
            arguments_schema=internet_current_arguments_schema(),
            runtime_binding="internet.current",
            discovery_group="internet",
            source_kind="internet",
            allowed_source_refs=current_sources,
            available=bool(current_sources),
            safety_reviewed=True,
            budget_cost=1,
            result_kind="external_information",
            activity_label="Searching current public information",
        ),
        CapabilityDefinition(
            capability_id=INTERNET_FETCH_URL_CAPABILITY_ID,
            purpose="Fetch one public HTTP URL",
            tool_id="internet",
            effect=EffectClass.READ,
            arguments_schema=internet_fetch_url_arguments_schema(),
            runtime_binding="internet.fetch_url",
            discovery_group="internet",
            source_kind="internet",
            allowed_source_refs=fetch_sources,
            available=bool(fetch_sources),
            safety_reviewed=True,
            budget_cost=1,
            result_kind="external_document",
            activity_label="Fetching public URL",
        ),
    )


def _calculator_capability() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=CALCULATOR_CAPABILITY_ID,
        purpose="Perform deterministic computation",
        tool_id="calculator",
        effect=EffectClass.READ,
        arguments_schema=calculator_arguments_schema(),
        runtime_binding="calculator.execute",
        discovery_group="calculator",
        available=True,
        safety_reviewed=True,
        budget_cost=1,
        result_kind="deterministic_result",
        activity_label="Calculating",
    )


def _arguments_schema(
    entry: Mapping[str, object],
) -> dict[str, object]:
    raw_specs = entry.get("parameter_specs")
    raw_parameters = entry.get("parameters")

    specs = {
        spec["name"]: spec
        for spec in _sequence(raw_specs)
        if isinstance(spec, Mapping)
        and isinstance(spec.get("name"), str)
        and spec["name"] not in {"action", "resource", "source"}
    }

    names = {
        name
        for name in _sequence(raw_parameters)
        if isinstance(name, str)
        and name not in {"action", "resource", "source"}
    }
    names.update(specs)

    properties = {
        name: _property_schema(specs.get(name))
        for name in sorted(names)
    }

    required = sorted(
        name
        for name, spec in specs.items()
        if spec.get("required") is True
    )

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _property_schema(
    spec: Mapping[str, object] | None,
) -> dict[str, object]:
    value_type = (
        spec.get("value_type")
        if spec is not None
        else "str"
    )

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

    result: dict[str, object] = {"type": json_type}

    if spec is None:
        return result

    enum = spec.get("enum")
    if (
        isinstance(enum, Sequence)
        and not isinstance(enum, (str, bytes))
        and enum
    ):
        result["enum"] = list(enum)

    for source_key in ("minimum", "maximum"):
        bound = spec.get(source_key)
        if type(bound) in {int, float}:
            result[source_key] = bound

    pattern = spec.get("pattern")
    if isinstance(pattern, str) and pattern:
        result["pattern"] = pattern

    return result


def _sequence(value: object) -> Sequence[object]:
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
    ):
        return value
    return ()


__all__ = [
    "AuthorityCatalog",
    "build_legacy_authority_catalog",
]
