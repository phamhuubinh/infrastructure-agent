from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True, slots=True)
class LifecycleTransition:
    """Immutable record of a lifecycle transition between two execution states."""
    from_state: "ExecutionState"
    to_state: "ExecutionState"
    timestamp: float
    metadata: Optional[dict[str, object]] = None
