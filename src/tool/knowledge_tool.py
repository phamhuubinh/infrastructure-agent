from __future__ import annotations

import inspect
from dataclasses import replace
from typing import TYPE_CHECKING

from src.pipeline.capability_library import (
    COVERS_TO_OPERATIONAL,
    validate_capability_support,
)
from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from src.tool.target_registry import TargetRegistry
from src.tool.tool import Tool

if TYPE_CHECKING:
    from src.pipeline.security.inspector_chain import InspectorChain


def _declared_capability(tool: Tool, resource: str) -> Capability | None:
    mod = inspect.getmodule(type(tool))
    if mod is None:
        return None
    raw = getattr(mod, "_CAPABILITIES", None)
    if not isinstance(raw, dict):
        return None
    capability = raw.get(resource)
    return capability if isinstance(capability, Capability) else None


def _default_inspector_chain(registry: TargetRegistry) -> InspectorChain:
    from src.pipeline.security.inspector_chain import InspectorChain
    from src.pipeline.security.parameter_safety_inspector import (
        ParameterSafetyInspector,
    )
    from src.pipeline.security.read_only_inspector import ReadOnlyInspector
    from src.pipeline.security.target_inspector import TargetInspector

    target_inspector = TargetInspector(safe_targets=set(registry.target_names()))
    return InspectorChain(
        [ReadOnlyInspector(), ParameterSafetyInspector(), target_inspector]
    )


def _complete_inspector_chain(
    registry: TargetRegistry, chain: InspectorChain | None
) -> InspectorChain:
    if chain is None:
        return _default_inspector_chain(registry)
    required = _default_inspector_chain(registry)
    present = {inspector.name for inspector in chain.inspectors}
    for inspector in required.inspectors:
        if inspector.name not in present:
            chain.add(inspector)
    return chain


def _tool_capabilities(tool: Tool) -> list[str]:
    """Return the list of capability names exposed by a Tool module.

    Used by get_capabilities() for lightweight name-only discovery.
    The full metadata (covers, category, intents, related) is available
    via get_capability_metadata().
    """
    mod = inspect.getmodule(type(tool))
    if mod is not None and hasattr(mod, "_CAPABILITIES"):
        return list(mod._CAPABILITIES.keys())
    return []


class KnowledgeTool(Tool):
    """Single dispatch entry point for all infrastructure tool execution.

    KnowledgeTool owns exactly one responsibility: route a (source, resource)
    pair to the correct Child Tool registered in the TargetRegistry.

    It does NOT:
    - access infrastructure directly
    - execute shell commands
    - know about individual tool implementations
    - perform reasoning or assessment

    Adding a new infrastructure domain (Docker, VMware, ...):
    - Create a new Child Tool class
    - Register it in the TargetRegistry (via tools.json or directly)
    - No changes needed in KnowledgeTool
    """

    def __init__(
        self,
        target_registry: TargetRegistry | None = None,
        inspector_chain: InspectorChain | None = None,
    ) -> None:
        if target_registry is None:
            target_registry = TargetRegistry()
            target_registry.add("localhost")
        self._registry = target_registry
        # Security is fail-closed and mandatory on every dispatch path.  Tests,
        # CLI, API, and direct runtime construction all receive the same chain.
        self._inspector_chain = _complete_inspector_chain(
            target_registry, inspector_chain
        )

    @staticmethod
    def get_operational_name(covers_tag: str) -> str | None:
        """Resolve a covers tag to an operational capability name."""
        return COVERS_TO_OPERATIONAL.get(covers_tag)

    def get_capabilities(self) -> dict[str, list[str]]:
        """Return mapping from target name to list of capability names.

        Lightweight discovery — returns only capability names.
        For full metadata (covers, category, intents), use
        get_capability_metadata().
        """
        caps: dict[str, list[str]] = {}
        for name in self._registry.target_names():
            tool = self._registry.get_tool(name)
            caps[name] = _tool_capabilities(tool)
        return caps

    def source_kind(self, source: str) -> str:
        """Return a credential-free provider kind for normalization."""

        tool = self._registry.get_tool(source)
        return type(tool).__name__.removesuffix("Tool").casefold()

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        source = arguments.get("source")
        resource = arguments.get("resource")

        if not isinstance(source, str):
            msg = "Missing source."
            raise ValueError(msg)

        if not isinstance(resource, str):
            msg = "Missing resource."
            raise ValueError(msg)

        try:
            child_tool = self._registry.get_tool(source)
        except KeyError:
            available = ", ".join(self._registry.target_names())

            return ToolResult(
                success=False,
                error=f"Unknown source: '{source}'. Available sources: {available}.",
            )

        declared = _declared_capability(child_tool, resource)

        # Security inspection: mandatory before preflight or child dispatch.
        from src.pipeline.security.tool_inspector import InspectionContext

        ctx = InspectionContext(
            capability_name=resource,
            target=source,
            resource=resource,
            arguments={
                k: v
                for k, v in arguments.items()
                if k not in ("source", "resource")
            },
            tool_name=type(child_tool).__name__,
            mutation_risk=(declared.mutation_risk if declared else "undeclared"),
        )
        inspection, inspection_receipt = self._inspector_chain.inspect_with_receipt(
            ctx
        )
        if inspection.denied or not inspection.allowed:
            return ToolResult(
                success=False,
                error=f"Security inspection blocked: {inspection.reason}",
                security_inspected=True,
                security_allowed=False,
                security_inspectors=inspection_receipt,
            )

        # Linux target preflight and metadata validation occur after security
        # inspection but before any capability-owned command is executed.
        backend = self._registry.backend(source)
        fingerprint = None
        if backend is not None:
            fingerprint = self._registry.preflight(source)
            if not fingerprint.reachable:
                return ToolResult(
                    success=False,
                    error=fingerprint.limitation,
                    capability_status=CapabilityStatus.COLLECTION_FAILED,
                    command_results=fingerprint.command_results,
                    security_inspected=True,
                    security_allowed=True,
                    security_inspectors=inspection_receipt,
                )
            if declared is not None:
                support = validate_capability_support(declared, fingerprint)
                if not support.supported:
                    return ToolResult(
                        success=False,
                        error=support.reason,
                        capability_status=CapabilityStatus.UNSUPPORTED,
                        warnings=(support.reason,),
                        security_inspected=True,
                        security_allowed=True,
                        security_inspectors=inspection_receipt,
                    )

        child_args: dict[str, object] = {"action": resource}
        extra = {k: v for k, v in arguments.items() if k not in ("source", "resource")}
        child_args.update(extra)

        child_result = child_tool.execute(child_args)
        return replace(
            child_result,
            security_inspected=True,
            security_allowed=True,
            security_inspectors=inspection_receipt,
        )

    def get_capability_metadata(self) -> dict[str, list[dict[str, object]]]:
        """Return full capability metadata for every registered target.

        Each capability entry includes:
        - name: the capability identifier
        - category: functional category (system, network, storage, ...)
        - intents: related investigation intents
        - related: related capability names (dependency hints)
        - covers: convention tags for operational capability routing
        - description: human-readable description
        - supported_targets: target types this capability supports
        - parameters: parameter names accepted by this capability
        - estimated_cost: estimated execution cost

        The handler field (implementation function) is intentionally
        excluded — it is an internal implementation detail of each tool.

        When a capability has multiple covers tags, each tag that resolves
        to an operational name produces a separate entry. This ensures
        multi-role capabilities (e.g., a trigger function that covers both
        "Alert Triggers" and "Alert Severity Assessment") register routes
        for all their operational names.
        """

        def _base_entry(value: Capability) -> dict[str, object]:
            return {
                "name": cap_name,
                "category": value.category,
                "intents": list(value.intents),
                "related": list(value.related),
                "covers": list(value.covers) if value.covers else [],
                "description": value.description,
                "supported_targets": list(value.supported_targets),
                "parameters": list(value.parameters),
                "parameter_specs": [
                    {
                        "name": spec.name,
                        "source": spec.source,
                        "required": spec.required,
                        "value_type": spec.value_type,
                        "default": spec.default,
                        "has_default": spec.has_default,
                        "enum": list(spec.enum),
                        "pattern": spec.pattern,
                        "minimum": spec.minimum,
                        "maximum": spec.maximum,
                    }
                    for spec in value.parameter_specs
                ],
                "preconditions": list(value.preconditions),
                "required_binaries": list(value.required_binaries),
                "required_any_binaries": list(value.required_any_binaries),
                "optional_binaries": list(value.optional_binaries),
                "supported_init_systems": list(value.supported_init_systems),
                "estimated_cost": value.estimated_cost,
                "expected_reliability": value.expected_reliability,
                "produces_facts": list(value.produces_facts),
                "mutation_risk": value.mutation_risk,
            }

        result: dict[str, list[dict[str, object]]] = {}
        for name in self._registry.target_names():
            tool = self._registry.get_tool(name)
            mod = inspect.getmodule(type(tool))
            if mod is None or not hasattr(mod, "_CAPABILITIES"):
                continue
            raw = mod._CAPABILITIES
            entries: list[dict[str, object]] = []
            for cap_name, value in raw.items():
                if isinstance(value, Capability):
                    if value.operational_name:
                        entry = _base_entry(value)
                        entry["operational_name"] = value.operational_name
                        entries.append(entry)
                    elif value.covers:
                        for tag in value.covers:
                            resolved = COVERS_TO_OPERATIONAL.get(tag)
                            if resolved:
                                entry = _base_entry(value)
                                entry["covers"] = [tag]
                                entry["operational_name"] = resolved
                                entries.append(entry)
                    else:
                        entry = _base_entry(value)
                        entry["operational_name"] = ""
                        entries.append(entry)
                else:
                    entries.append({"name": cap_name})
            if entries:
                result[name] = entries
        return result
