from __future__ import annotations

from dataclasses import dataclass

from .execution_state import ExecutionState


@dataclass(frozen=True, slots=True)
class LifecycleState:
    """Immutable snapshot of the current lifecycle status of an execution."""

    state: "ExecutionState"
    timestamp: float
    metadata: dict[str, object] | None = None
