from __future__ import annotations

from src.pipeline.capability_library import VALID_OPERATIONAL_NAMES
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
        self._route_candidates: dict[
            str, list[tuple[tuple[str, str], dict[str, object]]]
        ] = {}

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
        self._route_candidates.clear()
        metadata = knowledge_tool.get_capability_metadata()

        for source, capabilities in metadata.items():
            for cap_info in capabilities:
                tool_cap_name = str(cap_info["name"])
                op_name = cap_info.get("operational_name")

                if not isinstance(op_name, str) or not op_name:
                    continue
                # Only register if this operational capability exists in the library
                if op_name not in VALID_OPERATIONAL_NAMES:
                    continue
                route = (str(source), tool_cap_name)
                candidates = self._route_candidates.setdefault(op_name, [])
                if not any(existing[0] == route for existing in candidates):
                    candidates.append((route, dict(cap_info)))
                # Register compatibility route if not already registered.
                if op_name not in self._routes:
                    self._routes[op_name] = route

    def resolve(
        self,
        capability_name: str,
        extracted_params: object = None,
    ) -> tuple[str, str] | None:
        """Resolve an operational capability name to a KnowledgeTool route.

        Args:
            capability_name: The operational capability name.

        Returns:
            A (source, resource) tuple for KnowledgeTool dispatch,
            or None if no route is configured.
        """
        resolved = self.resolve_with_metadata(capability_name, extracted_params)
        return resolved[0] if resolved is not None else None

    def resolve_with_metadata(
        self,
        capability_name: str,
        extracted_params: object = None,
    ) -> tuple[tuple[str, str], dict[str, object]] | None:
        candidates = self._route_candidates.get(capability_name, [])
        if not candidates:
            route = self._routes.get(capability_name)
            return (route, {}) if route is not None else None
        params = self._param_dict(extracted_params)

        def _score(candidate):
            route, metadata = candidate
            raw_specs = metadata.get("parameter_specs", [])
            specs = raw_specs if isinstance(raw_specs, list) else []
            required_missing = 0
            matched = 0
            for spec in specs:
                if not isinstance(spec, dict):
                    continue
                source = str(spec.get("source") or spec.get("name") or "")
                present = self._source_value(params, source) is not None
                if present:
                    matched += 1
                elif bool(spec.get("required")) and not bool(spec.get("has_default")):
                    required_missing += 1
            resource = route[1]
            return (
                -required_missing,
                matched,
                int(not resource.startswith("search_")),
                -len(specs),
            )

        return max(candidates, key=_score)

    @staticmethod
    def _param_dict(extracted_params: object) -> dict[str, object]:
        if isinstance(extracted_params, dict):
            return dict(extracted_params)
        to_dict = getattr(extracted_params, "to_dict", None)
        if callable(to_dict):
            value = to_dict()
            if isinstance(value, dict):
                return dict(value)
        return {}

    @staticmethod
    def _source_value(params: dict[str, object], source: str) -> object | None:
        if source.startswith("timeframe."):
            timeframe = params.get("__timeframe__")
            return getattr(timeframe, source.partition(".")[2], None)
        return params.get(source)

    def available_routes(self) -> list[str]:
        """Return all configured capability names."""
        return sorted(self._routes)

    @property
    def route_count(self) -> int:
        """Return the number of configured routes."""
        return len(self._routes)
