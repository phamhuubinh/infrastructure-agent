from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class LifecycleState:
    """Immutable snapshot of the current lifecycle status of an execution."""
    state: "ExecutionState"
    timestamp: float
    metadata: dict[str, object] | None = None
