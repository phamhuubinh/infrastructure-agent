from __future__ import annotations

from src.infrastructure.ollama.ollama_client import OllamaClient
from src.model.model_adapter import ModelAdapter
from src.shared.execution.execution_plan import ExecutionPlan
from src.shared.execution.execution_step import ExecutionStep
from src.shared.execution.execution_step_result import (
    ExecutionStepResult,
)


class OllamaModelAdapter(ModelAdapter):
    """
    Model adapter backed by Ollama.
    """

    def __init__(
        self,
        client: OllamaClient,
    ) -> None:
        self._client = client

    def generate_execution_plan(
        self,
        user_request: str,
    ) -> ExecutionPlan:
        response = self._client.generate(
            self._build_execution_plan_prompt(
                user_request,
            )
        )

        command = response.strip()

        return ExecutionPlan(
            steps=(
                ExecutionStep(
                    step_type="cli",
                    payload=command,
                ),
            ),
        )

    def analyze_execution_results(
        self,
        results: tuple[ExecutionStepResult, ...],
    ) -> str:
        return self._client.generate(
            self._build_analysis_prompt(
                results,
            )
        ).strip()

    @staticmethod
    def _build_execution_plan_prompt(
        user_request: str,
    ) -> str:
        return f"""
You are a Linux system engineer.

Your task is to return exactly one shell command.

Rules:

- Return exactly one command.
- Do not explain.
- Do not use markdown.
- Do not wrap the command.
- Output only the command.

User request:

{user_request}
"""

    @staticmethod
    def _build_analysis_prompt(
        results: tuple[ExecutionStepResult, ...],
    ) -> str:
        return f"""
You are a Linux system engineer.

The following execution results were collected.

{results}

Explain the results to the user.
"""
