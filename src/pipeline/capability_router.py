from __future__ import annotations

from src.pipeline.capability_library import CAPABILITY_BY_EVIDENCE
from src.tool.knowledge_tool import KnowledgeTool


class CapabilityRouter:
    """Resolve operational capability names to KnowledgeTool routes.

    Routes are built dynamically from KnowledgeTool metadata at
    construction time. The router itself contains no hardcoded
    capability definitions — it is a pure lookup layer over the
    metadata provided by registered Child Tools.

    Capability definitions have exactly one source of truth:
    the Child Tool _CAPABILITIES declarations.
    """

    def __init__(self) -> None:
        self._routes: dict[str, tuple[str, str]] = {}

    def build_routes(self, knowledge_tool: KnowledgeTool) -> None:
        """Build route table from KnowledgeTool capability metadata.

        Scans every registered tool/source, reads its capabilities,
        and maps each capability's covers tags to operational
        capability names using the convention mapping.

        Args:
            knowledge_tool: The KnowledgeTool instance with registered
                            Child Tools.
        """
        self._routes.clear()
        metadata = knowledge_tool.get_capability_metadata()

        for source, capabilities in metadata.items():
            for cap_info in capabilities:
                tool_cap_name = cap_info["name"]
                op_name = cap_info.get("operational_name")

                if not op_name:
                    continue
                # Only register if this operational capability exists in the library
                if op_name not in CAPABILITY_BY_EVIDENCE.values():
                    continue
                # Register route if not already registered (first source wins)
                if op_name not in self._routes:
                    self._routes[op_name] = (source, tool_cap_name)

    def resolve(self, capability_name: str) -> tuple[str, str] | None:
        """Resolve an operational capability name to a KnowledgeTool route.

        Args:
            capability_name: The operational capability name.

        Returns:
            A (source, resource) tuple for KnowledgeTool dispatch,
            or None if no route is configured.
        """
        return self._routes.get(capability_name)

    def available_routes(self) -> list[str]:
        """Return all configured capability names."""
        return sorted(self._routes)

    @property
    def route_count(self) -> int:
        """Return the number of configured routes."""
        return len(self._routes)
