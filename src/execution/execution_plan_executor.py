from __future__ import annotations

import subprocess

from src.shared.execution.execution_plan import ExecutionPlan
from src.shared.execution.execution_step_result import (
    ExecutionStepResult,
)


def execute(
    plan: ExecutionPlan,
) -> tuple[ExecutionStepResult, ...]:
    """
    Execute an execution plan.

    MVP:
    - CLI only
    - Sequential execution
    """

    results: list[ExecutionStepResult] = []

    for step in plan.steps:
        completed = subprocess.run(
            step.payload,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )

        results.append(
            ExecutionStepResult(
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
            )
        )

    return tuple(results)
