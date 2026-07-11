from __future__ import annotations

from abc import ABC
from abc import abstractmethod

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
