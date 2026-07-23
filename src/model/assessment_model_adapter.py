from __future__ import annotations

from abc import ABC, abstractmethod

from src.pipeline.assessment_request import AssessmentRequest


class AssessmentModelAdapter(ABC):
    """Interface for assessment-only models.

    Unlike the legacy ModelAdapter (which produces Actions for tool
    calls), the AssessmentModelAdapter receives completed evidence and
    produces a final assessment string. It has no access to tools,
    capabilities, or execution context.
    """

    @abstractmethod
    def assess(self, assessment_request: AssessmentRequest) -> str:
        """Produce an assessment from collected evidence.

        Args:
            assessment_request: Completed evidence and context.

        Returns:
            A string containing the assessment, findings,
            and recommendations.
        """
        raise NotImplementedError

    def health_check(self, timeout: float = 5.0) -> bool:
        """Check if the model backend is reachable.

        Returns True if the backend responds, False otherwise.
        Default implementation returns True (always reachable for mock adapters).
        Override in subclasses for real connectivity checks.
        """
        return True

    def assess_raw(self, prompt: str) -> str:
        """Send a raw prompt to the model without evidence context.

        Used for general chat and question classification.
        Default implementation delegates to assess() with an empty request.
        Override in subclasses for direct LLM access.
        """
        from src.pipeline.assessment_request import AssessmentRequest

        return self.assess(AssessmentRequest(raw_request=prompt))
