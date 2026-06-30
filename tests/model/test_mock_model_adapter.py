from __future__ import annotations

from src.model.mock_model_adapter import MockModelAdapter
from src.shared.execution.execution_step_result import (
    ExecutionStepResult,
)


def test_generate_execution_plan() -> None:
    model = MockModelAdapter()

    plan = model.generate_execution_plan("hello")

    assert len(plan.steps) == 1
    assert plan.steps[0].step_type == "cli"
    assert plan.steps[0].payload == "echo hello"


def test_analyze_execution_results() -> None:
    model = MockModelAdapter()

    results = (
        ExecutionStepResult(
            stdout="hello\n",
            stderr="",
            exit_code=0,
        ),
    )

    assert model.analyze_execution_results(results) == "hello\n"
