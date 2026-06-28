from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True, slots=True)
class LifecycleState:
    """Immutable snapshot of the current lifecycle status of an execution."""
    state: "ExecutionState"
    timestamp: float
    metadata: Optional[dict[str, object]] = None
