from __future__ import annotations

from dataclasses import dataclass

from .execution_state import ExecutionState


@dataclass(frozen=True, slots=True)
class LifecycleTransition:
    """Immutable record of a lifecycle transition between two execution states."""

    from_state: "ExecutionState"
    to_state: "ExecutionState"
    timestamp: float
    metadata: dict[str, object] | None = None
