from __future__ import annotations

from benchmark.assessment_evaluator import (
    AssessmentExpected,
    AssessmentMetrics,
    evaluate,
    metrics_to_dict,
)


class TestEvaluate:
    def test_empty_response_fails_without_fabricated_consistency(self) -> None:
        metrics = evaluate("", AssessmentExpected())

        assert metrics.grounding == 0.0
        assert metrics.consistency == 0.0
        assert metrics.length == 0
        assert metrics.passed is False

    def test_allowed_claims_must_be_present(self) -> None:
        expected = AssessmentExpected(
            allowed_claims=("CPU usage is 42%", "Memory usage is 50%"),
            allowed_numbers=(42, 50),
            sections=("Summary",),
        )

        metrics = evaluate("Summary: CPU usage is 42%.", expected)

        assert metrics.allowed_claim_coverage == 0.5
        assert metrics.grounding == 0.5
        assert metrics.passed is False

    def test_reviewed_claims_and_numbers_pass(self) -> None:
        expected = AssessmentExpected(
            allowed_claims=("CPU usage is 42%", "Memory usage is 50%"),
            allowed_numbers=(42, 50),
            recommendations=("Monitor memory"),
            sections=("Summary", "Recommendations"),
        )
        response = (
            "Summary: CPU usage is 42%; Memory usage is 50%.\n"
            "Recommendations: Monitor memory."
        )

        metrics = evaluate(response, expected)

        assert metrics.allowed_claim_coverage == 1.0
        assert metrics.consistency == 1.0
        assert metrics.unsupported_claim_count == 0
        assert metrics.passed is True

    def test_hallucinated_long_response_fails_on_forbidden_and_unknown_value(
        self,
    ) -> None:
        expected = AssessmentExpected(
            allowed_claims=("CPU usage is 42%", "Memory usage is 50%"),
            allowed_numbers=(42, 50),
            forbidden_claims=("Disk is 99% full",),
            recommendations=("Monitor memory",),
            sections=("Summary", "Assessment", "Risks", "Recommendations"),
        )
        response = (
            "Summary: CPU usage is 42%; Memory usage is 50%.\n"
            "Assessment: The system is stable.\n"
            "Risks: Disk is 99% full and will fail tomorrow.\n"
            "Recommendations: Monitor memory. "
            "This otherwise very long, polished explanation repeats the same unsupported conclusion."
        )

        metrics = evaluate(response, expected)

        assert metrics.allowed_claim_coverage == 1.0
        assert metrics.unsupported_claim_count >= 2
        assert metrics.consistency == 0.0
        assert metrics.grounding == 0.0
        assert metrics.passed is False

    def test_legacy_evidence_fields_remain_compatible(self) -> None:
        metrics = evaluate(
            "CPU is healthy. Memory is sufficient.",
            AssessmentExpected(evidence=("CPU", "Memory", "Disk")),
        )

        assert abs(metrics.evidence_coverage - (2.0 / 3.0)) < 0.001
        assert abs(metrics.allowed_claim_coverage - (2.0 / 3.0)) < 0.001


class TestAssessmentMetrics:
    def test_defaults_are_non_passing(self) -> None:
        metrics = AssessmentMetrics()

        assert metrics.consistency == 0.0
        assert metrics.overall == 0.0
        assert metrics.passed is False

    def test_frozen(self) -> None:
        import pytest

        metrics = AssessmentMetrics()
        with pytest.raises(AttributeError):
            metrics.grounding = 0.5  # type: ignore[misc]


class TestMetricsToDict:
    def test_conversion_includes_claim_and_gate_signals(self) -> None:
        data = metrics_to_dict(
            AssessmentMetrics(
                evidence_coverage=0.8,
                recommendation_coverage=0.5,
                grounding=0.75,
                completeness=1.0,
                consistency=1.0,
                allowed_claim_coverage=0.75,
                unsupported_claim_count=0,
                length=500,
                overall=0.81,
                passed=True,
            )
        )

        assert data["allowed_claim_coverage"] == 0.75
        assert data["unsupported_claim_count"] == 0
        assert data["passed"] is True
