from __future__ import annotations

from src.pipeline.investigation_request import InvestigationRequest
from src.tool.target_registry import TargetRegistry


class TargetResolver:
    """Resolve investigation target from user request.

    Responsibilities:
    - read user request, extract target name
    - match against registered targets (from TargetRegistry)
    - fall back to "localhost" if no explicit target is found

    Never performs execution or evidence collection.
    """

    def __init__(self, target_registry: TargetRegistry | None = None) -> None:
        self._registry = target_registry

    def resolve(self, request: InvestigationRequest) -> None:
        """Resolve the target for the given investigation request.

        Scans the request for known target/domain-tool names.
        Falls back to "localhost" if nothing matches.

        Args:
            request: InvestigationRequest. Mutates request.target.
        """
        raw = request.raw_request.lower()

        # Collect all registered names (targets + domain tools).
        known_names: list[str] = []
        if self._registry is not None:
            known_names = self._registry.target_names()

        # Sort by length descending so more specific names match first
        # (e.g. "monitor-zabbix" before "monitor").
        for name in sorted(known_names, key=len, reverse=True):
            if name.lower() in raw:
                request.target = name
                return

        # Default fallback.
        request.target = "localhost"
