from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.execution.execution_step_result import (
    ExecutionStepResult,
)


def test_execution_step_result_stores_result() -> None:
    result = ExecutionStepResult(
        result="stdout",
    )

    assert result.result == "stdout"


def test_execution_step_result_is_immutable() -> None:
    result = ExecutionStepResult(
        result="stdout",
    )

    with pytest.raises(FrozenInstanceError):
        result.result = "changed"  # type: ignore[misc]
