from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.execution.execution_step import ExecutionStep


def test_execution_step_stores_values() -> None:
    step = ExecutionStep(
        step_type="cli",
        payload="docker ps",
    )

    assert step.step_type == "cli"
    assert step.payload == "docker ps"


def test_execution_step_is_immutable() -> None:
    step = ExecutionStep(
        step_type="cli",
        payload="docker ps",
    )

    with pytest.raises(FrozenInstanceError):
        step.step_type = "api"  # type: ignore[misc]
