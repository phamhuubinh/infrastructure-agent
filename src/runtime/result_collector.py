from __future__ import annotations

from src.shared.execution.execution_result import ExecutionResult
from src.shared.execution.execution_state import ExecutionState
from src.shared.execution.runtime_metadata import RuntimeMetadata


class ResultCollector:
    """
    ResultCollector assembles the immutable execution result
    for a single execution.
    """

    def collect(
        self,
        execution_reference: str,
        state: ExecutionState,
        output: object | None,
        error: str | None,
        metadata: RuntimeMetadata,
    ) -> ExecutionResult:
        """
        Assemble the immutable execution result.
        """
        return ExecutionResult(
            execution_id=execution_reference,
            state=state,
            output=output,
            error=error,
            metadata=metadata,
        )
