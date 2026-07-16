from __future__ import annotations

from unittest import mock

from benchmark.registry import (
    _get_nested,
    _metadata_matches,
    _next_run_id,
    detect_regressions,
    save_results,
)


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
        "scores": {
            "total": total,
            "reasoning": 1.0,
            "efficiency": 1.0,
            "evidence": 1.0,
            "safety": 1.0,
        },
        "assessment_metrics": {
            "overall": assessment_overall,
            "evidence_coverage": evidence_coverage,
            "grounding": grounding,
            "completeness": completeness,
            "consistency": 1.0,
            "length": 100,
        },
    }


def _make_meta(model: str, server: str = "") -> dict:
    return {
        "model": model,
        "server": server,
        "provider": "",
        "benchmark_version": "1.0",
    }


class TestNextRunId:
    def test_empty_history_returns_1(self) -> None:
        assert _next_run_id({}) == "1"

    def test_single_entry(self) -> None:
        assert _next_run_id({"1": {}}) == "2"

    def test_past_9_entries(self) -> None:
        history = {str(i): {} for i in range(1, 11)}
        assert _next_run_id(history) == "11"

    def test_mixed_keys(self) -> None:
        history = {"1": {}, "2": {}, "10": {}}
        assert _next_run_id(history) == "11"

    def test_non_digit_key_ignored(self) -> None:
        history = {"1": {}, "abc": {}}
        assert _next_run_id(history) == "2"


class TestMetadataMatches:
    def test_both_none(self) -> None:
        assert _metadata_matches(None, None) is True

    def test_one_none(self) -> None:
        assert _metadata_matches({"model": "a"}, None) is True
        assert _metadata_matches(None, {"model": "a"}) is True

    def test_same_model_server(self) -> None:
        m1 = _make_meta("gpt-4", "sv1")
        m2 = _make_meta("gpt-4", "sv1")
        assert _metadata_matches(m1, m2) is True

    def test_different_model(self) -> None:
        m1 = _make_meta("gpt-4")
        m2 = _make_meta("claude")
        assert _metadata_matches(m1, m2) is False

    def test_different_server(self) -> None:
        m1 = _make_meta("gpt-4", "sv1")
        m2 = _make_meta("gpt-4", "sv2")
        assert _metadata_matches(m1, m2) is False


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
            total_regs = [r for r in regressions if r["metric"] == "total"]
            assert len(total_regs) == 1

    def test_assessment_overall_decrease_detected(self) -> None:
        prev = [_make_result("test_bm", total=0.95, assessment_overall=0.8)]
        new = [_make_result("test_bm", total=0.95, assessment_overall=0.5)]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assessment_regs = [
                r for r in regressions if r["metric"] == "assessment_overall"
            ]
            assert len(assessment_regs) == 1

    def test_mismatched_model_skips_regression(self) -> None:
        """When previous run has different model, regression should be skipped."""
        prev = [_make_result("test_bm", total=0.95, assessment_overall=0.8)]
        new = [_make_result("test_bm", total=0.50, assessment_overall=0.2)]
        history = {"1": {"results": prev, "metadata": _make_meta("model-a")}}
        new_meta = _make_meta("model-b")

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new, new_metadata=new_meta)
            assert len(regressions) == 0

    def test_matched_model_detects_regression(self) -> None:
        prev = [_make_result("test_bm", total=0.95, assessment_overall=0.8)]
        new = [_make_result("test_bm", total=0.50, assessment_overall=0.2)]
        history = {"1": {"results": prev, "metadata": _make_meta("model-a")}}
        new_meta = _make_meta("model-a")

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new, new_metadata=new_meta)
            assert len(regressions) >= 2  # total + assessment_overall

    def test_picks_most_recent_matching_run(self) -> None:
        """Should compare against most recent run with matching model, not last run overall."""
        prev_a = [_make_result("bm", total=0.95)]  # old model-a
        prev_b = [_make_result("bm", total=0.90)]  # recent model-b
        new = [_make_result("bm", total=0.50)]
        new_meta = _make_meta("model-a")
        history = {
            "1": {"results": prev_a, "metadata": _make_meta("model-a")},
            "2": {"results": prev_b, "metadata": _make_meta("model-b")},
        }

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new, new_metadata=new_meta)
            total_regs = [r for r in regressions if r["metric"] == "total"]
            # Should compare against run 1 (model-a), not run 2 (model-b)
            assert len(total_regs) == 1
            # Delta should be 0.95 → 0.50 = -0.45, not 0.90 → 0.50
            assert total_regs[0]["previous"] == 0.95

    def test_legacy_without_metadata_falls_back_to_last(self) -> None:
        """Runs without metadata should compare against last run (backward compat)."""
        prev = [_make_result("bm", total=0.95)]
        new = [_make_result("bm", total=0.70)]
        history = {"1": {"results": prev}}

        with mock.patch("benchmark.registry.load_history", return_value=history):
            regressions = detect_regressions(new)
            assert len(regressions) == 1

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
    def test_save_creates_entry(
        self, mock_write: mock.Mock, mock_load: mock.Mock
    ) -> None:
        results = [_make_result("test_bm", total=0.95)]
        history = save_results(results)
        assert "1" in history
        assert history["1"]["overall"] == 0.95
