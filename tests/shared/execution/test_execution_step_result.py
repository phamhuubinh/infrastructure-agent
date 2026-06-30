from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.execution.execution_step_result import (
    ExecutionStepResult,
)


def test_execution_step_result_stores_values() -> None:
    result = ExecutionStepResult(
        stdout="stdout",
        stderr="stderr",
        exit_code=0,
    )

    assert result.stdout == "stdout"
    assert result.stderr == "stderr"
    assert result.exit_code == 0


def test_execution_step_result_is_immutable() -> None:
    result = ExecutionStepResult(
        stdout="stdout",
        stderr="stderr",
        exit_code=0,
    )

    with pytest.raises(FrozenInstanceError):
        result.stdout = "changed"  # type: ignore[misc]
