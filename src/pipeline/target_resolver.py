from __future__ import annotations

import difflib
from typing import ClassVar

from src.pipeline.investigation_request import InvestigationRequest
from src.tool.target_registry import TargetRegistry


class TargetResolver:
    """Resolve investigation target from user request.

    Responsibilities:
    - read user request, extract target name
    - match against registered targets (from TargetRegistry)
    - use intent-based default when no explicit target is found
    - fall back to "localhost" for non-monitoring intents

    Never performs execution or evidence collection.
    """

    # Common aliases for hostnames and services.
    _ALIASES: ClassVar[dict[str, str]] = {
        "server": "server01",
        "server1": "server01",
        "server02": "server02",
        "server2": "server02",
        "db": "database",
        "database": "database",
        "monitor": "zabbix",
        "monitoring": "zabbix",
        "mon": "zabbix",
        "zabbix_server": "zabbix",
        "zabbix-server": "zabbix",
        "graphana": "grafana",
        "graphan": "grafana",
    }

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
        domain_tools = {"zabbix", "grafana", "prometheus"}
        if self._registry is not None:
            known_names = self._registry.target_names()

        # Check aliases first (fastest path).
        for word in raw.split():
            word = word.strip(",.!?;:'\"()[]{}<>")
            alias_target = self._ALIASES.get(word)
            if alias_target and alias_target in known_names:
                request.target = alias_target
                if alias_target.lower() not in domain_tools:
                    from src.pipeline.intent_resolver import Intent
                    request.intent = Intent.MACHINE_ASSESSMENT
                return

        # Exact substring match (fast path).
        for name in sorted(known_names, key=len, reverse=True):
            if name.lower() in raw:
                request.target = name
                if name.lower() not in domain_tools:
                    from src.pipeline.intent_resolver import Intent
                    request.intent = Intent.MACHINE_ASSESSMENT
                return

        # Fuzzy match for typos (slow path).
        words = raw.split()
        best_name: str | None = None
        best_ratio: float = 0.0
        for name in known_names:
            for word in words:
                clean_word = word.strip(",.!?;:'\"()[]{}<>")
                ratio = difflib.SequenceMatcher(None, name.lower(), clean_word).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_name = name
        if best_name is not None and best_ratio >= 0.6:
            request.target = best_name
            if best_name.lower() not in domain_tools:
                from src.pipeline.intent_resolver import Intent
                request.intent = Intent.MACHINE_ASSESSMENT
            return

        # Step 2: Intent + keyword-based defaults.
        if intent is not None and self._registry is not None:
            intent_name = intent.name

            # Dashboard/panel questions -> prefer grafana
            if intent_name == "MONITORING_ASSESSMENT":
                if any(kw in raw for kw in ("dashboard", "panel", "grafana", "biểu đồ", "đồ thị")):
                    if "grafana" in known_names:
                        request.target = "grafana"
                        return
                # Everything else monitoring -> prefer zabbix
                for preferred in ("zabbix", "grafana"):
                    if preferred in known_names:
                        request.target = preferred
                        return

        # Step 3: Fallback.
        request.target = "localhost"
