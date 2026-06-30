from __future__ import annotations

from src.model.model_adapter import ModelAdapter
from src.shared.execution.execution_plan import ExecutionPlan
from src.shared.execution.execution_step import ExecutionStep
from src.shared.execution.execution_step_result import (
    ExecutionStepResult,
)


class MockModelAdapter(ModelAdapter):
    """
    Minimal reasoning model used for MVP testing.
    """

    def generate_execution_plan(
        self,
        user_request: str,
    ) -> ExecutionPlan:
        return ExecutionPlan(
            steps=(
                ExecutionStep(
                    step_type="cli",
                    payload=f"echo {user_request}",
                ),
            ),
        )

    def analyze_execution_results(
        self,
        results: tuple[ExecutionStepResult, ...],
    ) -> str:
        return results[0].stdout
