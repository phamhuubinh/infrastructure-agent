from __future__ import annotations

from datetime import datetime

from src.runtime.result_dispatcher import ResultDispatcher
from src.shared.execution.execution_result import ExecutionResult
from src.shared.execution.execution_state import ExecutionState
from src.shared.execution.runtime_metadata import RuntimeMetadata


def test_dispatch_returns_true() -> None:
    dispatched: list[ExecutionResult] = []

    def consumer(result: ExecutionResult) -> None:
        dispatched.append(result)

    metadata = RuntimeMetadata(
        runtime_version="1.0",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        duration_ms=1,
    )

    result = ExecutionResult(
        execution_id="execution-1",
        state=ExecutionState.COMPLETED,
        output="success",
        error=None,
        metadata=metadata,
    )

    dispatcher = ResultDispatcher()

    assert dispatcher.dispatch(result, consumer) is True
    assert dispatched == [result]


def test_dispatch_returns_false_when_target_is_not_callable() -> None:
    metadata = RuntimeMetadata(
        runtime_version="1.0",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        duration_ms=1,
    )

    result = ExecutionResult(
        execution_id="execution-1",
        state=ExecutionState.COMPLETED,
        output="success",
        error=None,
        metadata=metadata,
    )

    dispatcher = ResultDispatcher()

    assert dispatcher.dispatch(result, object()) is False
