from __future__ import annotations

from src.shared.execution.execution_result import ExecutionResult


class ResultDispatcher:
    """
    ResultDispatcher delivers immutable execution results
    to downstream consumers.
    """

    def dispatch(
        self,
        execution_result: ExecutionResult,
        dispatch_target: object,
    ) -> bool:
        """
        Dispatch an immutable execution result.
        """
        if not callable(dispatch_target):
            return False

        try:
            dispatch_target(execution_result)
        except Exception:
            return False

        return True
