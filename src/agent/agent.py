from __future__ import annotations

from src.execution.execution_plan_executor import execute
from src.model.model_adapter import ModelAdapter


class Agent:
    """
    Coordinates interactions between the reasoning model
    and the execution runtime.
    """

    def __init__(self, model: ModelAdapter) -> None:
        self._model = model

    def run(self, user_request: str) -> str:
        plan = self._model.generate_execution_plan(user_request)
        results = execute(plan)
        return self._model.analyze_execution_results(results)
