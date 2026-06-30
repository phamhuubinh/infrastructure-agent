from __future__ import annotations

from src.execution.execution_plan_executor import execute
from src.shared.execution.execution_plan import ExecutionPlan
from src.shared.execution.execution_step import ExecutionStep


def test_execute_echo_hello() -> None:
    plan = ExecutionPlan(
        steps=(
            ExecutionStep(
                step_type="cli",
                payload="echo hello",
            ),
        ),
    )

    results = execute(plan)

    assert len(results) == 1
    assert results[0].stdout == "hello\n"
    assert results[0].stderr == ""
    assert results[0].exit_code == 0
