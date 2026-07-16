from __future__ import annotations

import difflib
from typing import ClassVar

from src.pipeline.investigation_request import InvestigationRequest
from src.tool.target_registry import TargetRegistry


class UnknownTargetError(ValueError):
    """Raised when the user explicitly mentions a target that does not exist."""

    def __init__(self, raw_target: str, available: list[str]) -> None:
        self.raw_target = raw_target
        self.available = available
        if available:
            super().__init__(
                f"Unknown target: '{raw_target}'.\n"
                f"Did you mean: {', '.join(sorted(available))}"
            )
        else:
            super().__init__(f"Unknown target: '{raw_target}'.\nNo targets configured.")


class TargetResolver:
    """Resolve investigation target from user request.

    Responsibilities:
    - read user request, extract target name
    - match against registered targets (from TargetRegistry)
    - use intent-based default when no explicit target is found
    - raise UnknownTargetError when user names a non-existent target

    Never performs execution or evidence collection.
    """

    # Common aliases for hostnames and services.
    _ALIASES: ClassVar[dict[str, str]] = {
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

    @staticmethod
    def _extract_words(raw: str) -> list[str]:
        return [w.strip(",.!?;:'\"()[]{}<>") for w in raw.split()]

    def resolve(self, request: InvestigationRequest) -> None:
        """Resolve the target for the given investigation request.

        Scans the request for known target/domain-tool names first.
        If no explicit match, uses intent + keyword-based defaults.

        Args:
            request: InvestigationRequest. Mutates request.target.

        Raises:
            UnknownTargetError: if a word in the request matches an alias but the
                                resolved target does not exist, or if no matching
                                target is found and no default applies.
        """
        raw = request.raw_request.lower()
        intent = request.intent

        known_names: list[str] = []
        if self._registry is not None:
            known_names = self._registry.target_names()

        words = self._extract_words(raw)

        # Step 1: Check aliases (fastest path).
        for word in words:
            alias_target = self._ALIASES.get(word)
            if alias_target:
                if alias_target in known_names:
                    request.target = alias_target
                    return
                raise UnknownTargetError(alias_target, known_names)

        # Step 2: Exact substring match (fast path).
        for name in sorted(known_names, key=len, reverse=True):
            if name.lower() in raw:
                request.target = name
                return

        # Step 3: Fuzzy match for typos (slow path).
        best_name: str | None = None
        best_ratio: float = 0.0
        for name in known_names:
            for word in words:
                ratio = difflib.SequenceMatcher(None, name.lower(), word).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_name = name
        if best_name is not None and best_ratio >= 0.6:
            request.target = best_name
            return

        # Step 4: Intent + keyword-based defaults.
        if intent is not None and self._registry is not None:
            intent_name = intent.name

            # Dashboard/panel questions -> prefer grafana
            if intent_name == "MONITORING_ASSESSMENT":
                if any(
                    kw in raw
                    for kw in ("dashboard", "panel", "grafana", "biểu đồ", "đồ thị")
                ):
                    if "grafana" in known_names:
                        request.target = "grafana"
                        return
                # Everything else monitoring -> prefer zabbix
                for preferred in ("zabbix", "grafana"):
                    if preferred in known_names:
                        request.target = preferred
                        return

        # Step 5: Check if user explicitly named a target via preposition.
        # If the request mentions "on <name>" or "for <name>" and that
        # name looks like a hostname, raise UnknownTargetError.
        _prepositions = frozenset({"on", "for", "at", "from"})
        _skip_words = frozenset(
            {
                "the",
                "a",
                "an",
                "is",
                "are",
                "was",
                "were",
                "check",
                "show",
                "get",
                "list",
                "find",
                "what",
                "how",
                "why",
                "when",
                "where",
                "in",
                "with",
                "of",
                "to",
                "and",
                "or",
                "but",
                "not",
                "all",
                "cpu",
                "memory",
                "disk",
                "network",
                "storage",
                "system",
                "alert",
                "alerts",
                "problem",
                "problems",
                "service",
                "services",
                "status",
                "health",
                "performance",
                "security",
                "config",
                "monitor",
                "monitoring",
                "dashboard",
                "dashboards",
                "host",
                "hosts",
                "process",
                "processes",
                "package",
                "packages",
            }
        )
        for i, word in enumerate(words):
            if word in _prepositions and i + 1 < len(words):
                candidate = words[i + 1]
                if len(candidate) > 2 and candidate not in _skip_words:
                    raise UnknownTargetError(candidate, known_names)

        # Step 6: Fallback — no explicit target found.
        request.target = "localhost"
