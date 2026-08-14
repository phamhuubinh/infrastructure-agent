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

        facts = tuple(request.fact_set.facts)
        findings = tuple(request.findings)

        unknowns = tuple(
            dict.fromkeys(
                (
                    *(missing for finding in findings for missing in finding.missing_facts),
                    *request.missing_evidence,
                )
            )
        )

        evidence_status_name = ""
        status = getattr(request, "evidence_status", None)
        if status is not None:
            evidence_status_name = status.name

        allowed_claims = tuple(
            dict.fromkeys(
                (
                    *(fact.id for fact in facts if fact.usable),
                    *(
                        fact.id
                        for package in request.evidence
                        for fact in package.facts
                        if fact.usable
                    ),
                    *(finding.id for finding in findings),
                )
            )
        )

        request_frame_summary: dict[str, object] | None = None
        frame = getattr(request, "request_frame", None)
        if frame is not None and hasattr(frame, "to_dict"):
            request_frame_summary = frame.to_dict()

        return AssessmentRequest(
            raw_request=request.raw_request,
            intent=intent_name,
            evidence=tuple(request.evidence),
            evidence_complete=request.evidence_complete,
            missing_evidence=request.missing_evidence,
            facts=facts,
            collection_failures=tuple(
                failure
                for package in request.evidence
                for failure in package.collection_failures
            ),
            findings=findings,
            health_summary=request.health_summary,
            request_frame=request_frame_summary,
            unknowns=unknowns,
            evidence_status=evidence_status_name,
            allowed_claims=allowed_claims,
            raw_evidence_required=any(
                package.valid_for_requirements and not package.facts
                for package in request.evidence
            ),
        )
