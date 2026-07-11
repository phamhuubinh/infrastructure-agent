from __future__ import annotations

import time as _time

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.assessment_result import AssessmentResult
from src.model.llm_client import LLMClient
from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_request import AssessmentRequest


class LLMAssessmentAdapter(AssessmentModelAdapter):
    """Production assessment adapter using a real LLM.

    Responsibilities:
    - receive AssessmentRequest
    - build prompt via PromptBuilderV2
    - call LLM via LLMClient
    - return AssessmentResult

    No investigation logic.
    No tool execution.
    No ReAct.
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def assess(self, assessment_request: AssessmentRequest) -> str:
        """Produce an assessment from collected evidence.

        Current implementation returns AssessmentResult.content as string
        for backward compatibility with DeterministicAgent.

        Args:
            assessment_request: Completed evidence and context.

        Returns:
            A string containing the assessment from the model.
        """
        result = self._assess_with_result(assessment_request)
        return result.content

    def assess_with_result(
        self,
        assessment_request: AssessmentRequest,
    ) -> AssessmentResult:
        """Produce an assessment and return a structured result.

        Args:
            assessment_request: Completed evidence and context.

        Returns:
            An AssessmentResult with content, success status, and metadata.
        """
        return self._assess_with_result(assessment_request)

    def _assess_with_result(
        self,
        assessment_request: AssessmentRequest,
    ) -> AssessmentResult:
        """Internal implementation shared by assess() and assess_with_result()."""
        t0 = _time.perf_counter()

        try:
            prompt = build_assessment_prompt(assessment_request)
        except Exception as exc:
            return AssessmentResult(
                content="",
                success=False,
                model=self._client._model,
                error=f"Prompt construction failed: {exc}",
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        try:
            response = self._client.generate(prompt)
        except Exception as exc:
            return AssessmentResult(
                content="",
                success=False,
                model=self._client._model,
                error=f"LLM call failed: {exc}",
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        latency = round((_time.perf_counter() - t0) * 1000, 1)

        usage = self._client.last_usage
        return AssessmentResult(
            content=response,
            success=True,
            model=self._client._model,
            latency_ms=latency,
            prompt_tokens=usage.get("prompt_tokens") if usage else None,
            completion_tokens=usage.get("completion_tokens") if usage else None,
        )
