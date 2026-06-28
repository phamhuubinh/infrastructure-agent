from dataclasses import dataclass
from typing import Any

from .execution_state import ExecutionState
from .runtime_metadata import RuntimeMetadata

@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Represents the outcome of an execution.

    Attributes:
        execution_id: Unique identifier for the execution.
        state: Current state of the execution (e.g., COMPLETED, FAILED).
        output: The result of the execution, if any.
        error: Error message if the execution failed.
        metadata: Additional runtime metadata associated with the execution.
    """

    execution_id: str
    state: ExecutionState
    output: Any
    error: str
    metadata: RuntimeMetadata
