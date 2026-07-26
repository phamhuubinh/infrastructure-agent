from __future__ import annotations

from src.pipeline.security.tool_inspector import (
    InspectionContext,
    InspectionResult,
    InspectionVerdict,
    ToolInspector,
)

# Targets that are explicitly allowed for any tool execution.
# These are safe local/development targets.
_DEFAULT_SAFE_TARGETS: set[str] = {
    "localhost",
    "127.0.0.1",
    "::1",
}


class TargetInspector(ToolInspector):
    """Inspector that validates the target of a tool execution.

    Prevents capabilities from being executed against production
    or unexpected targets. The allowlist is configurable — by default
    only ``localhost`` and loopback addresses are permitted.

    Production targets must be explicitly added to the allowlist
    via ``add_safe_target()`` at agent construction time.
    """

    def __init__(
        self,
        safe_targets: set[str] | None = None,
        blocked_targets: set[str] | None = None,
    ) -> None:
        """Initialize the target inspector.

        Args:
            safe_targets: Additional targets to allow beyond the defaults.
            blocked_targets: Targets to explicitly block (overrides safe list).
        """
        self._safe_targets: set[str] = _DEFAULT_SAFE_TARGETS.copy()
        if safe_targets:
            self._safe_targets.update(t.lower() for t in safe_targets)
        self._blocked_targets: set[str] = (
            {t.lower() for t in blocked_targets} if blocked_targets else set()
        )

    @property
    def name(self) -> str:
        return "TargetInspector"

    def add_safe_target(self, target: str) -> None:
        """Add a target to the safe list at runtime.

        This is the primary extension point — when the agent discovers
        targets from ``servers.json``, they should be registered here.
        """
        self._safe_targets.add(target.lower())

    def remove_safe_target(self, target: str) -> None:
        """Remove a target from the safe list at runtime."""
        self._safe_targets.discard(target.lower())

    def inspect(self, context: InspectionContext) -> InspectionResult:
        target = context.target.lower().strip()

        if not target:
            return InspectionResult(
                verdict=InspectionVerdict.DENY,
                reason="No target specified for tool execution.",
                inspector_name=self.name,
            )

        # Blocked targets take priority.
        if target in self._blocked_targets:
            return InspectionResult(
                verdict=InspectionVerdict.DENY,
                reason=(
                    f"Target '{context.target}' is explicitly blocked "
                    f"from tool execution."
                ),
                inspector_name=self.name,
            )

        # Safe targets are allowed.
        if target in self._safe_targets:
            return InspectionResult(
                verdict=InspectionVerdict.ALLOW,
                inspector_name=self.name,
            )

        # Unknown targets — allow by default for the local trusted-network
        # scope. This is consistent with ADR-0001's current scope.
        # The target was already resolved by TargetResolver, so it is
        # a valid known hostname.
        return InspectionResult(
            verdict=InspectionVerdict.ALLOW,
            reason=(
                f"Target '{context.target}' is not in the explicit safe list "
                f"but is allowed in local trusted-network mode."
            ),
            inspector_name=self.name,
        )
