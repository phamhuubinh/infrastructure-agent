from __future__ import annotations

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.providers.fallback_chain import FallbackChain
from src.pipeline.assessment_request import AssessmentRequest


class FallbackAssessmentAdapter(AssessmentModelAdapter):
    """Assessment adapter that applies the configured provider chain."""

    def __init__(self, adapters: list[AssessmentModelAdapter]) -> None:
        self._fallback = FallbackChain(adapters)

    @property
    def adapters(self) -> list[AssessmentModelAdapter]:
        return self._fallback.chain

    def assess(self, assessment_request: AssessmentRequest) -> str:
        return str(
            self._fallback.execute_with_fallback(
                lambda adapter: adapter.assess(assessment_request)
            )
        )

    def assess_raw(self, prompt: str) -> str:
        return str(
            self._fallback.execute_with_fallback(
                lambda adapter: adapter.assess_raw(prompt)
            )
        )

    def health_check(self, timeout: float = 5.0) -> bool:
        for adapter in self.adapters:
            try:
                if adapter.health_check(timeout=timeout):
                    return True
            except Exception:
                continue
        return False
