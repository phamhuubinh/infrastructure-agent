from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any


@dataclass(frozen=True, slots=True)
class AssessmentExpected:
    """Expected assessment characteristics for a benchmark scenario.

    All fields are deterministic keyword lists — no exact wording comparison.
    """

    evidence: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    sections: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AssessmentMetrics:
    """Deterministic metrics computed from an assessment response."""

    evidence_coverage: float = 0.0
    recommendation_coverage: float = 0.0
    grounding: float = 0.0
    completeness: float = 0.0
    consistency: float = 1.0
    length: int = 0
    overall: float = 0.0


# Weights for overall score calculation.
# Configurable — change these constants to adjust weighting.
_WEIGHT_EVIDENCE = 0.30
_WEIGHT_RECOMMENDATION = 0.20
_WEIGHT_GROUNDING = 0.20
_WEIGHT_COMPLETENESS = 0.20
_WEIGHT_CONSISTENCY = 0.10


def _keyword_match_count(
    text: str,
    keywords: tuple[str, ...],
) -> int:
    """Count how many keywords appear in the text (case-insensitive)."""
    lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lower)


def evaluate(
    response: str,
    expected: AssessmentExpected,
    prompt_size: int = 0,
    completion_size: int = 0,
) -> AssessmentMetrics:
    """Compute deterministic assessment metrics from a response.

    No AI. No HTTP. No prompt generation. Pure deterministic evaluation.

    Args:
        response: The assessment text from the model.
        expected: Expected assessment characteristics.
        prompt_size: Size of the prompt in bytes (for reporting).
        completion_size: Size of the response in bytes (for reporting).

    Returns:
        AssessmentMetrics with all computed scores.
    """
    if not response:
        return AssessmentMetrics()

    # Evidence coverage
    total_evidence = len(expected.evidence)
    matched_evidence = _keyword_match_count(response, expected.evidence)
    evidence_coverage = (
        matched_evidence / total_evidence if total_evidence > 0 else 1.0
    )

    # Recommendation coverage
    total_recs = len(expected.recommendations)
    matched_recs = _keyword_match_count(response, expected.recommendations)
    recommendation_coverage = matched_recs / total_recs if total_recs > 0 else 1.0

    # Grounding: checks whether response references evidence by name
    grounding_score = 0.0
    if total_evidence > 0:
        # Count how many evidence items are referenced AND the response
        # explicitly mentions data values (numbers, percentages, etc.)
        has_data_values = any(c.isdigit() for c in response)
        grounding_evidence = (
            _keyword_match_count(response, expected.evidence) / total_evidence
        )
        if has_data_values and grounding_evidence >= 0.5:
            grounding_score = min(1.0, grounding_evidence + 0.2)
        else:
            grounding_score = grounding_evidence

    # Completeness: whether required sections are present
    total_sections = len(expected.sections)
    matched_sections = _keyword_match_count(response, expected.sections)
    completeness = matched_sections / total_sections if total_sections > 0 else 1.0

    # Overall weighted score
    overall = (
        evidence_coverage * _WEIGHT_EVIDENCE
        + recommendation_coverage * _WEIGHT_RECOMMENDATION
        + grounding_score * _WEIGHT_GROUNDING
        + completeness * _WEIGHT_COMPLETENESS
        + 1.0 * _WEIGHT_CONSISTENCY  # consistency is always 1.0 for now
    )
    overall = max(0.0, min(1.0, overall))

    return AssessmentMetrics(
        evidence_coverage=round(evidence_coverage, 4),
        recommendation_coverage=round(recommendation_coverage, 4),
        grounding=round(grounding_score, 4),
        completeness=round(completeness, 4),
        consistency=1.0,
        length=len(response),
        overall=round(overall, 4),
    )


def metrics_to_dict(metrics: AssessmentMetrics) -> dict[str, float]:
    """Convert AssessmentMetrics to a flat dict for JSON serialization."""
    return {
        "evidence_coverage": metrics.evidence_coverage,
        "recommendation_coverage": metrics.recommendation_coverage,
        "grounding": metrics.grounding,
        "completeness": metrics.completeness,
        "consistency": metrics.consistency,
        "length": metrics.length,
        "overall": metrics.overall,
    }
