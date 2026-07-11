from __future__ import annotations

from unittest import mock

from benchmark.registry import _get_nested, detect_regressions, save_results


def _make_result(
    benchmark: str,
    total: float,
    assessment_overall: float = 0.0,
    evidence_coverage: float = 0.0,
    grounding: float = 0.0,
    completeness: float = 0.0,
) -> dict:
    return {
        "benchmark": benchmark,
        "scores": {"total": total, "reasoning": 1.0, "efficiency": 1.0, "evidence": 1.0, "safety": 1.0},
        "assessment_metrics": {
            "overall": assessment_overall,
            "evidence_coverage": evidence_coverage,
            "grounding": grounding,
            "completeness": completeness,
            "consistency": 1.0,
            "length": 100,
        },
    }


class TestGetNested:
    def test_simple_key(self) -> None:
        d = {"scores": {"total": 0.95}}
        assert _get_nested(d, "scores.total") == 0.95

    def test_assessment_metric(self) -> None:
        d = {"assessment_metrics": {"overall": 0.8}}
        assert _get_nested(d, "assessment_metrics.overall") == 0.8

    def test_missing_key_returns_zero(self) -> None:
        d = {"scores": {"total": 0.95}}
        assert _get_nested(d, "assessment_metrics.overall") == 0.0

    def test_missing_nested_dict(self) -> None:
        d = {}
        assert _get_nested(d, "scores.total") == 0.0

    def test_non_numeric_returns_zero(self) -> None:
        d = {"scores": {"total": "not_a_number"}}
        assert _get_nested(d, "scores.total") == 0.0


class TestDetectRegressions:
    def test_no_history_returns_empty(self) -> None:
        with mock.patch("benchmark.registry.load_history", return_value={}):
            regressions = detect_regressions([])
            assert regressions == []

    def test_total_decrease_detected(self) -> None:
        prev = [_make_result("test_bm", total=0.95)]
        new = [_make_result("test_bm", total=0.70)]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assert len(regressions) >= 1
            # At least one regression with metric="total"
            total_regs = [r for r in regressions if r["metric"] == "total"]
            assert len(total_regs) == 1
            assert total_regs[0]["benchmark"] == "test_bm"

    def test_assessment_overall_decrease_detected(self) -> None:
        prev = [_make_result("test_bm", total=0.95, assessment_overall=0.8)]
        new = [_make_result("test_bm", total=0.95, assessment_overall=0.5)]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assessment_regs = [r for r in regressions if r["metric"] == "assessment_overall"]
            assert len(assessment_regs) == 1
            assert assessment_regs[0]["delta"] <= -0.15

    def test_evidence_coverage_decrease_detected(self) -> None:
        prev = [_make_result("test_bm", total=0.95, evidence_coverage=0.9)]
        new = [_make_result("test_bm", total=0.95, evidence_coverage=0.3)]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            ev_regs = [r for r in regressions if r["metric"] == "evidence_coverage"]
            assert len(ev_regs) == 1

    def test_grounding_decrease_detected(self) -> None:
        prev = [_make_result("test_bm", total=0.95, grounding=0.8)]
        new = [_make_result("test_bm", total=0.95, grounding=0.4)]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            grd_regs = [r for r in regressions if r["metric"] == "grounding"]
            assert len(grd_regs) == 1

    def test_multiple_regressions_detected(self) -> None:
        prev = [_make_result(
            "test_bm", total=0.95, assessment_overall=0.8,
            evidence_coverage=0.9, grounding=0.8, completeness=0.9,
        )]
        new = [_make_result(
            "test_bm", total=0.70, assessment_overall=0.4,
            evidence_coverage=0.3, grounding=0.3, completeness=0.3,
        )]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assert len(regressions) >= 3  # total + at least 2 assessment metrics

    def test_legacy_benchmark_without_assessment_metrics(self) -> None:
        """Regression should still work for benchmarks without assessment metrics."""
        prev = [{"benchmark": "test_bm", "scores": {"total": 0.95}}]
        new = [{"benchmark": "test_bm", "scores": {"total": 0.70}}]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assert len(regressions) == 1
            assert regressions[0]["metric"] == "total"

    def test_zero_assessment_metrics_skipped(self) -> None:
        """When previous run had 0 assessment metrics, don't flag regression."""
        prev = [_make_result("test_bm", total=0.95)]
        new = [_make_result("test_bm", total=0.95)]
        history = {"1": {"results": prev}}

        # Both have assessment_overall=0.0 — should be skipped
        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assessment_regs = [r for r in regressions if "assessment" in r["metric"]]
            assert len(assessment_regs) == 0

    def test_no_regression_when_improved(self) -> None:
        prev = [_make_result("test_bm", total=0.70)]
        new = [_make_result("test_bm", total=0.95)]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assert len(regressions) == 0

    def test_new_benchmark_not_flagged(self) -> None:
        prev = [_make_result("old_bm", total=0.95)]
        new = [_make_result("new_bm", total=0.50)]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assert len(regressions) == 0


class TestSaveResults:
    @mock.patch("benchmark.registry.load_history", return_value={})
    @mock.patch("benchmark.registry.Path.write_text")
    def test_save_creates_entry(self, mock_write: mock.Mock, mock_load: mock.Mock) -> None:
        results = [_make_result("test_bm", total=0.95)]
        history = save_results(results)
        assert "1" in history
        assert history["1"]["overall"] == 0.95
