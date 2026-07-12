from __future__ import annotations

from src.pipeline.investigation_request import InvestigationRequest
from src.tool.target_registry import TargetRegistry


class TargetResolver:
    """Resolve investigation target from user request.

    Responsibilities:
    - read user request, extract target name
    - match against registered targets (from TargetRegistry)
    - use intent-based default when no explicit target is found
    - fall back to "localhost"

    Never performs execution or evidence collection.
    """

    def __init__(self, target_registry: TargetRegistry | None = None) -> None:
        self._registry = target_registry

    def resolve(self, request: InvestigationRequest) -> None:
        """Resolve the target for the given investigation request.

        Scans the request for known target/domain-tool names first.
        If no explicit match, uses intent + keyword-based defaults.

        Args:
            request: InvestigationRequest. Mutates request.target.
        """
        raw = request.raw_request.lower()
        intent = request.intent

        # Step 1: Try explicit name matching from registry.
        known_names: list[str] = []
        if self._registry is not None:
            known_names = self._registry.target_names()

        for name in sorted(known_names, key=len, reverse=True):
            if name.lower() in raw:
                request.target = name
                return

        # Step 2: Intent + keyword-based defaults.
        if intent is not None and self._registry is not None:
            intent_name = intent.name

            # Dashboard/panel questions → prefer grafana
            if intent_name == "MONITORING_ASSESSMENT":
                if any(kw in raw for kw in ("dashboard", "panel", "grafana")):
                    if "grafana" in known_names:
                        request.target = "grafana"
                        return
                # Everything else monitoring → prefer zabbix
                for preferred in ("zabbix", "grafana"):
                    if preferred in known_names:
                        request.target = preferred
                        return

        # Step 3: Fallback.
        request.target = "localhost"
