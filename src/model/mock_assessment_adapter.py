from __future__ import annotations

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_request import AssessmentRequest


class MockAssessmentAdapter(AssessmentModelAdapter):
    """Mock assessment adapter for testing.

    Returns a summary of the evidence without calling a real model.
    Useful for testing the pipeline without LLM dependencies.
    """

    def assess(self, assessment_request: AssessmentRequest) -> str:
        """Return a structured summary of collected evidence.

        This is NOT a real assessment — it's a deterministic summary
        for testing pipeline integration.
        """
        evidence_count = len(assessment_request.evidence)
        success_count = sum(1 for e in assessment_request.evidence if e.success)
        failed_count = evidence_count - success_count

        lines: list[str] = [
            f"Investigation: {assessment_request.raw_request}",
            f"Intent: {assessment_request.intent}",
            f"Evidence collected: {evidence_count}",
            f"  Successful: {success_count}",
            f"  Failed: {failed_count}",
            f"Evidence complete: {assessment_request.evidence_complete}",
        ]

        if assessment_request.missing_evidence:
            lines.append(
                f"Missing evidence: {', '.join(assessment_request.missing_evidence)}"
            )

        return "\n".join(lines)
