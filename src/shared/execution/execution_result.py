from dataclasses import dataclass
from typing import Any

from .execution_state import ExecutionState
from .runtime_metadata import RuntimeMetadata


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Immutable execution result for a single execution."""

    execution_id: str
    state: ExecutionState
    output: Any
    error: str | None
    metadata: RuntimeMetadata
