from __future__ import annotations

import time as _time
from dataclasses import replace

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.assessment_result import AssessmentResult
from src.model.llm_client import LLMClient
from src.model.protocol.orion_system_prompt import ORION_SYSTEM_PROMPT
from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.input_context_budget import InputContextBudget
from src.shared.logger import info as _info

# Backward-compatible name: the fixed Orion system instruction is shared with
# input-context budget enforcement in the provider-neutral protocol layer.
_ORION_SYSTEM_PROMPT = ORION_SYSTEM_PROMPT


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
        # Provider-neutral estimate of the most recent call's input context,
        # computed at prompt construction.  None = unknown (no call yet).
        self._last_input_estimate: int | None = None

    @property
    def last_usage(self) -> ModelCallUsage | None:
        """Client-reported usage with the provider-neutral input estimate.

        Provider-reported token fields are never overwritten or
        reinterpreted; the estimate is attached as a separate field.
        """

        usage = self._client.last_usage
        if usage is None or self._last_input_estimate is None:
            return usage
        return replace(usage, estimated_input_tokens=self._last_input_estimate)

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

    def assess_raw(self, prompt: str) -> str:
        """Send a raw prompt to the LLM without evidence wrapper."""
        t0 = _time.perf_counter()
        # Estimate at the construction boundary, before the provider call.
        self._last_input_estimate = InputContextBudget.estimated_tokens(
            _ORION_SYSTEM_PROMPT + prompt
        )
        try:
            response = self._client.generate(
                prompt,
                system_prompt=_ORION_SYSTEM_PROMPT,
            )
            latency = round((_time.perf_counter() - t0) * 1000, 1)
            usage = self._client.last_usage
            _info(
                "llm",
                status="success",
                mode="raw",
                duration_ms=latency,
                input_tokens=usage.input_tokens if usage else "N/A",
                reasoning_tokens=usage.reasoning_tokens if usage else "N/A",
                output_tokens=usage.visible_output_tokens if usage else "N/A",
                message="LLM raw response received",
            )
            return response
        except Exception as exc:
            latency = round((_time.perf_counter() - t0) * 1000, 1)
            _info(
                "llm",
                status="error",
                mode="raw",
                duration_ms=latency,
                error=str(exc)[:80],
                message="LLM raw call failed",
            )
            raise

    def _assess_with_result(
        self,
        assessment_request: AssessmentRequest,
    ) -> AssessmentResult:
        """Internal implementation shared by assess() and assess_with_result()."""
        t0 = _time.perf_counter()
        self._last_input_estimate = None

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
        # Estimate at the construction boundary, before the provider call.
        self._last_input_estimate = InputContextBudget.estimated_tokens(
            _ORION_SYSTEM_PROMPT + prompt
        )

        try:
            response = self._client.generate(
                prompt,
                system_prompt=_ORION_SYSTEM_PROMPT,
                purpose="assessment",
            )
        except Exception as exc:
            _info(
                "llm",
                status="error",
                error=str(exc)[:80],
                duration_ms=round((_time.perf_counter() - t0) * 1000, 1),
                message="LLM call failed",
            )
            return AssessmentResult(
                content="",
                success=False,
                model=self._client._model,
                error=f"LLM call failed: {exc}",
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        latency = round((_time.perf_counter() - t0) * 1000, 1)

        usage = self._client.last_usage
        pt = usage.input_tokens if usage else None
        ct = usage.visible_output_tokens if usage else None
        _info(
            "llm",
            status="success",
            duration_ms=latency,
            input_tokens=pt or "N/A",
            output_tokens=ct or "N/A",
            message="LLM response received",
        )
        return AssessmentResult(
            content=response,
            success=True,
            model=self._client._model,
            latency_ms=latency,
            prompt_tokens=pt,
            completion_tokens=ct,
        )
