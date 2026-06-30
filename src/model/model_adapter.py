from __future__ import annotations

from abc import ABC, abstractmethod

from src.shared.execution.execution_plan import ExecutionPlan
from src.shared.execution.execution_step_result import (
    ExecutionStepResult,
)


class ModelAdapter(ABC):
    """
    Interface for reasoning models.
    """

    @abstractmethod
    def generate_execution_plan(
        self,
        user_request: str,
    ) -> ExecutionPlan:
        """
        Generate an execution plan from a user request.
        """
        raise NotImplementedError

    @abstractmethod
    def analyze_execution_results(
        self,
        results: tuple[ExecutionStepResult, ...],
    ) -> str:
        """
        Produce a response from raw execution results.
        """
        raise NotImplementedError
