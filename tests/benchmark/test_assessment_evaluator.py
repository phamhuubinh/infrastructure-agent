from __future__ import annotations

from benchmark.assessment_evaluator import (
    AssessmentExpected,
    AssessmentMetrics,
    evaluate,
    metrics_to_dict,
)


class TestEvaluate:
    def test_empty_response(self) -> None:
        metrics = evaluate("", AssessmentExpected())
        assert metrics.evidence_coverage == 0.0
        assert metrics.recommendation_coverage == 0.0
        assert metrics.grounding == 0.0
        assert metrics.completeness == 0.0
        assert metrics.length == 0

    def test_evidence_coverage_all_matched(self) -> None:
        response = "CPU is healthy. Memory is sufficient. Disk has space."
        expected = AssessmentExpected(
            evidence=("CPU", "Memory", "Disk"),
        )
        metrics = evaluate(response, expected)
        assert metrics.evidence_coverage == 1.0

    def test_evidence_coverage_partial(self) -> None:
        response = "CPU is healthy."
        expected = AssessmentExpected(
            evidence=("CPU", "Memory", "Disk"),
        )
        metrics = evaluate(response, expected)
        assert abs(metrics.evidence_coverage - (1.0 / 3.0)) < 0.001

    def test_evidence_coverage_none(self) -> None:
        response = "Everything is fine."
        expected = AssessmentExpected(
            evidence=("CPU", "Memory"),
        )
        metrics = evaluate(response, expected)
        assert metrics.evidence_coverage == 0.0

    def test_recommendation_coverage(self) -> None:
        response = "Recommendation: clean up disk space. Monitor memory usage."
        expected = AssessmentExpected(
            recommendations=("clean up", "monitor", "upgrade"),
        )
        metrics = evaluate(response, expected)
        assert abs(metrics.recommendation_coverage - (2.0 / 3.0)) < 0.001

    def test_completeness_all_sections(self) -> None:
        response = (
            "Summary: System is healthy.\n"
            "Assessment: All subsystems OK.\n"
            "Risks: None identified.\n"
            "Recommendations: Continue monitoring."
        )
        expected = AssessmentExpected(
            sections=("Summary", "Assessment", "Risks", "Recommendations"),
        )
        metrics = evaluate(response, expected)
        assert metrics.completeness == 1.0

    def test_completeness_partial(self) -> None:
        response = "Summary: System is healthy."
        expected = AssessmentExpected(
            sections=("Summary", "Assessment", "Risks", "Recommendations"),
        )
        metrics = evaluate(response, expected)
        assert abs(metrics.completeness - (1.0 / 4.0)) < 0.001

    def test_grounding_with_data_values(self) -> None:
        response = (
            "CPU usage is 45%. Memory usage is 8GB out of 16GB (50%). "
            "Disk /dev/sda1 is at 75% capacity."
        )
        expected = AssessmentExpected(
            evidence=("CPU", "Memory", "Disk"),
        )
        metrics = evaluate(response, expected)
        assert metrics.grounding > 0.5  # Should have bonus for data values

    def test_grounding_without_data_values(self) -> None:
        response = "CPU is fine. Memory is OK. Disk has space."
        expected = AssessmentExpected(
            evidence=("CPU", "Memory", "Disk"),
        )
        metrics = evaluate(response, expected)
        assert metrics.grounding == 1.0  # All evidence matched, no bonus needed
        assert metrics.grounding <= 1.0

    def test_case_insensitive(self) -> None:
        response = "cpu information: 4 cores. MEMORY: 8GB. disk: 256GB."
        expected = AssessmentExpected(
            evidence=("CPU", "Memory", "Disk"),
        )
        metrics = evaluate(response, expected)
        assert metrics.evidence_coverage == 1.0

    def test_overall_score_default_weights(self) -> None:
        """Perfect response should give overall = 1.0."""
        response = (
            "Summary: CPU is 45%. Memory is 8GB. Disk is 75%.\n"
            "Assessment: All subsystems are within normal ranges.\n"
            "Risks: Disk may need attention soon.\n"
            "Recommendations: Clean up disk. Monitor memory."
        )
        expected = AssessmentExpected(
            evidence=("CPU", "Memory", "Disk"),
            recommendations=("clean up", "monitor"),
            sections=("Summary", "Assessment", "Risks", "Recommendations"),
        )
        metrics = evaluate(response, expected)
        assert metrics.overall > 0.5
        assert metrics.overall <= 1.0

    def test_overall_zero_for_empty(self) -> None:
        metrics = evaluate("", AssessmentExpected())
        assert metrics.overall == 0.0


class TestAssessmentMetrics:
    def test_defaults(self) -> None:
        m = AssessmentMetrics()
        assert m.evidence_coverage == 0.0
        assert m.recommendation_coverage == 0.0
        assert m.grounding == 0.0
        assert m.completeness == 0.0
        assert m.consistency == 1.0
        assert m.length == 0
        assert m.overall == 0.0

    def test_frozen(self) -> None:
        m = AssessmentMetrics()
        import pytest
        with pytest.raises(AttributeError):
            m.evidence_coverage = 0.5  # type: ignore[misc]


class TestMetricsToDict:
    def test_conversion(self) -> None:
        m = AssessmentMetrics(
            evidence_coverage=0.8,
            recommendation_coverage=0.5,
            grounding=0.75,
            completeness=1.0,
            consistency=1.0,
            length=500,
            overall=0.81,
        )
        d = metrics_to_dict(m)
        assert d["evidence_coverage"] == 0.8
        assert d["recommendation_coverage"] == 0.5
        assert d["grounding"] == 0.75
        assert d["overall"] == 0.81
