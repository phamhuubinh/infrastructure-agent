from datetime import datetime
from dataclasses import dataclass
from typing import Any

from shared.execution.execution_state import ExecutionState


@dataclass(frozen=True, slots=True)
class ExecutionSession:
    """Groups one or more executions into a single execution lifecycle."""

    session_id: str
    execution_ids: tuple[str, ...]
    created_at: datetime
    state: ExecutionState
    metadata: dict[str, Any]
