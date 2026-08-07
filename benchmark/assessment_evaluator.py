from __future__ import annotations

"""Deterministic assessment evaluator based on allowed claims.

The evaluator deliberately scores *claims that the fixture says are allowed*,
rather than rewarding a response for being long or containing generic section
headings.  It remains lexical and offline by design: fixtures provide the
human-reviewed phrases and numeric values that may appear in an answer.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssessmentExpected:
    """Human-reviewed claims and presentation requirements for one scenario.

    ``allowed_claims`` are grounded facts/findings that may be stated.  When
    non-empty, ``required_claims`` defaults to the same set so a response
    cannot pass merely by adding attractive prose around an unsupported
    conclusion.  ``allowed_numbers`` catches the common failure mode where a
    response names the right metric but invents its value.

    The older evidence/recommendation fields are retained only for existing
    benchmark datasets; new QA fixtures should use the claim fields.
    """

    allowed_claims: tuple[str, ...] = ()
    required_claims: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    allowed_numbers: tuple[str | int | float, ...] = ()
    evidence: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    sections: tuple[str, ...] = ()

    @property
    def required_grounded_claims(self) -> tuple[str, ...]:
        return self.required_claims or self.allowed_claims or self.evidence


@dataclass(frozen=True, slots=True)
class AssessmentMetrics:
    """Deterministic quality signals computed from an assessment response."""

    evidence_coverage: float = 0.0
    recommendation_coverage: float = 0.0
    grounding: float = 0.0
    completeness: float = 0.0
    consistency: float = 0.0
    allowed_claim_coverage: float = 0.0
    unsupported_claim_count: int = 0
    length: int = 0
    overall: float = 0.0
    passed: bool = False


_WEIGHT_EVIDENCE = 0.25
_WEIGHT_RECOMMENDATION = 0.15
_WEIGHT_GROUNDING = 0.25
_WEIGHT_COMPLETENESS = 0.15
_WEIGHT_CONSISTENCY = 0.20
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?%?")


def _keyword_match_count(text: str, keywords: tuple[str, ...]) -> int:
    """Count case-insensitive reviewed phrases present in a response."""
    lower = text.casefold()
    return sum(1 for keyword in keywords if keyword.casefold() in lower)


def _coverage(text: str, expected: tuple[str, ...]) -> float:
    if not expected:
        return 1.0
    return _keyword_match_count(text, expected) / len(expected)


def _normalise_number(value: str | int | float) -> str:
    raw = str(value).strip().casefold()
    if raw.endswith("%"):
        raw = raw[:-1]
    try:
        numeric = float(raw)
    except ValueError:
        return raw
    return str(int(numeric)) if numeric.is_integer() else str(numeric)


def _unsupported_claim_count(response: str, expected: AssessmentExpected) -> int:
    """Count explicitly forbidden claims and numeric values absent from facts."""
    violations = _keyword_match_count(response, expected.forbidden_claims)
    if not expected.allowed_numbers:
        return violations

    allowed = {_normalise_number(value) for value in expected.allowed_numbers}
    for token in _NUMBER.findall(response):
        if _normalise_number(token) not in allowed:
            violations += 1
    return violations


def evaluate(
    response: str,
    expected: AssessmentExpected,
    prompt_size: int = 0,
    completion_size: int = 0,
) -> AssessmentMetrics:
    """Evaluate an answer against reviewed claims without an LLM or network.

    ``prompt_size`` and ``completion_size`` remain accepted for compatibility
    with benchmark callers.  They are intentionally not quality signals.
    """
    del prompt_size, completion_size
    if not response or not response.strip():
        return AssessmentMetrics(length=len(response))

    required_claims = expected.required_grounded_claims
    allowed_claim_coverage = _coverage(response, required_claims)
    evidence_coverage = _coverage(response, expected.evidence)
    recommendation_coverage = _coverage(response, expected.recommendations)
    completeness = _coverage(response, expected.sections)
    unsupported_claims = _unsupported_claim_count(response, expected)
    consistency = 1.0 if unsupported_claims == 0 else 0.0

    # Grounding only receives full credit when every required claim is present
    # and no unsupported claim was emitted.  This prevents a long hallucinated
    # answer from passing via headings, length, or a few correct keywords.
    grounding = allowed_claim_coverage if unsupported_claims == 0 else 0.0
    overall = (
        evidence_coverage * _WEIGHT_EVIDENCE
        + recommendation_coverage * _WEIGHT_RECOMMENDATION
        + grounding * _WEIGHT_GROUNDING
        + completeness * _WEIGHT_COMPLETENESS
        + consistency * _WEIGHT_CONSISTENCY
    )
    overall = max(0.0, min(1.0, overall))
    passed = (
        allowed_claim_coverage == 1.0
        and consistency == 1.0
        and completeness == 1.0
        and recommendation_coverage == 1.0
    )

    return AssessmentMetrics(
        evidence_coverage=round(evidence_coverage, 4),
        recommendation_coverage=round(recommendation_coverage, 4),
        grounding=round(grounding, 4),
        completeness=round(completeness, 4),
        consistency=consistency,
        allowed_claim_coverage=round(allowed_claim_coverage, 4),
        unsupported_claim_count=unsupported_claims,
        length=len(response),
        overall=round(overall, 4),
        passed=passed,
    )


def metrics_to_dict(metrics: AssessmentMetrics) -> dict[str, float | int | bool]:
    """Convert metrics to a flat, JSON-serializable record."""
    return {
        "evidence_coverage": metrics.evidence_coverage,
        "recommendation_coverage": metrics.recommendation_coverage,
        "grounding": metrics.grounding,
        "completeness": metrics.completeness,
        "consistency": metrics.consistency,
        "allowed_claim_coverage": metrics.allowed_claim_coverage,
        "unsupported_claim_count": metrics.unsupported_claim_count,
        "length": metrics.length,
        "overall": metrics.overall,
        "passed": metrics.passed,
    }
