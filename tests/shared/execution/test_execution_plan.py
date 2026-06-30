from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.execution.execution_plan import ExecutionPlan
from src.shared.execution.execution_step import ExecutionStep


def test_execution_plan_stores_steps() -> None:
    step = ExecutionStep(
        step_type="cli",
        payload="docker ps",
    )

    plan = ExecutionPlan(
        steps=(step,),
    )

    assert len(plan.steps) == 1


def test_execution_plan_is_immutable() -> None:
    plan = ExecutionPlan(
        steps=(),
    )

    with pytest.raises(FrozenInstanceError):
        plan.steps = ()  # type: ignore[misc]
