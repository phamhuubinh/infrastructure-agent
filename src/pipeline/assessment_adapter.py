from __future__ import annotations

from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.investigation_request import InvestigationRequest


class AssessmentAdapter:
    """Convert InvestigationRequest into AssessmentRequest.

    Responsibilities:
    - extract evidence and context from the pipeline
    - produce an immutable AssessmentRequest for the model
    - keep runtime objects invisible to the Assessment Model

    Never performs reasoning or assessment.
    """

    def build(self, request: InvestigationRequest) -> AssessmentRequest:
        """Build an AssessmentRequest from an InvestigationRequest.

        Args:
            request: The completed InvestigationRequest from the pipeline.

        Returns:
            An AssessmentRequest containing only the information the
            Assessment Model needs.
        """
        intent_name = ""
        if request.intent is not None:
            intent_name = request.intent.name

        return AssessmentRequest(
            raw_request=request.raw_request,
            intent=intent_name,
            evidence=tuple(request.evidence),
            evidence_complete=request.evidence_complete,
            missing_evidence=request.missing_evidence,
        )
