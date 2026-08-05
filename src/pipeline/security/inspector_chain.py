from __future__ import annotations

from src.pipeline.security.tool_inspector import (
    InspectionContext,
    InspectionResult,
    InspectionVerdict,
    ToolInspector,
)


class InspectorChain:
    """Ordered chain of security inspectors for tool execution.

    Inspectors run in registration order. The chain stops at the first
    DENY or REQUIRE_APPROVAL result. ALLOW results continue to the
    next inspector.

    Usage::

        chain = InspectorChain()
        chain.add(ReadOnlyInspector())
        chain.add(ParameterSafetyInspector())
        result = chain.inspect(context)
        if result.denied:
            return ToolResult(success=False, error=result.reason)
    """

    def __init__(self, inspectors: list[ToolInspector] | None = None) -> None:
        self._inspectors: list[ToolInspector] = list(inspectors) if inspectors else []

    def add(self, inspector: ToolInspector) -> None:
        """Append an inspector to the end of the chain."""
        self._inspectors.append(inspector)

    def insert(self, index: int, inspector: ToolInspector) -> None:
        """Insert an inspector at a specific position."""
        self._inspectors.insert(index, inspector)

    def remove(self, inspector_name: str) -> bool:
        """Remove an inspector by name. Returns True if removed."""
        for i, insp in enumerate(self._inspectors):
            if insp.name == inspector_name:
                del self._inspectors[i]
                return True
        return False

    @property
    def inspectors(self) -> list[ToolInspector]:
        """Return a copy of the inspector list."""
        return list(self._inspectors)

    def inspect(self, context: InspectionContext) -> InspectionResult:
        """Run all inspectors in order, stopping at first non-ALLOW verdict.

        Args:
            context: The execution context for this tool dispatch.

        Returns:
            The first non-ALLOW InspectionResult, or an ALLOW result
            if all inspectors pass.
        """
        for inspector in self._inspectors:
            result = inspector.inspect(context)
            if result.verdict != InspectionVerdict.ALLOW:
                return result

        return InspectionResult(
            verdict=InspectionVerdict.ALLOW,
            reason="All inspectors passed.",
            inspector_name="InspectorChain",
        )

    def inspect_all(self, context: InspectionContext) -> list[InspectionResult]:
        """Run all inspectors and return all results (for audit purposes).

        Unlike ``inspect()``, this does not short-circuit on DENY.
        Useful for logging or audit trails where you want to see
        which inspectors would have blocked the execution.
        """
        return [inspector.inspect(context) for inspector in self._inspectors]

    def inspect_with_receipt(
        self, context: InspectionContext
    ) -> tuple[InspectionResult, tuple[str, ...]]:
        """Inspect and return the exact ordered inspectors that ran.

        The receipt is deliberately name-only: it is safe for execution traces
        and proves that a dispatch crossed the complete security boundary
        without exposing user parameters or target credentials.
        """

        executed: list[str] = []
        for inspector in self._inspectors:
            executed.append(inspector.name)
            result = inspector.inspect(context)
            if result.verdict != InspectionVerdict.ALLOW:
                return result, tuple(executed)
        return (
            InspectionResult(
                verdict=InspectionVerdict.ALLOW,
                reason="All inspectors passed.",
                inspector_name="InspectorChain",
            ),
            tuple(executed),
        )
