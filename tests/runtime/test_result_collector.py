from __future__ import annotations

from datetime import datetime

from src.runtime.result_collector import ResultCollector
from src.shared.execution.execution_state import ExecutionState
from src.shared.execution.runtime_metadata import RuntimeMetadata


def test_collect_returns_execution_result() -> None:
    collector = ResultCollector()

    metadata = RuntimeMetadata(
        runtime_version="1.0",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        duration_ms=10,
    )

    result = collector.collect(
        execution_reference="execution-1",
        state=ExecutionState.COMPLETED,
        output="success",
        error=None,
        metadata=metadata,
    )

    assert result.execution_id == "execution-1"
    assert result.state is ExecutionState.COMPLETED
    assert result.output == "success"
    assert result.error is None
    assert result.metadata == metadata
