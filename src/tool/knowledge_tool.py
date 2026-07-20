from __future__ import annotations

import inspect

from src.pipeline.capability_library import COVERS_TO_OPERATIONAL
from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.target_registry import TargetRegistry
from src.tool.tool import Tool


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
    ) -> None:
        if target_registry is None:
            target_registry = TargetRegistry()
            target_registry.add("localhost")
        self._registry = target_registry

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

        child_args: dict[str, object] = {"action": resource}
        extra = {k: v for k, v in arguments.items() if k not in ("source", "resource")}
        child_args.update(extra)

        return child_tool.execute(child_args)

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
                "estimated_cost": value.estimated_cost,
            }

        result: dict[str, list[dict[str, object]]] = {}
        for name in self._registry.target_names():
            tool = self._registry.get_tool(name)
            mod = inspect.getmodule(type(tool))
            if mod is None or not hasattr(mod, "_CAPABILITIES"):
                continue
            raw = getattr(mod, "_CAPABILITIES")
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
