from __future__ import annotations

from src.pipeline.threshold_evaluator import ThresholdEvaluator


def test_cpu_warning() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate({"cpu_usage": 85.0}) == "warning"


def test_cpu_critical() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate({"cpu_usage": 95.0}) == "critical"


def test_disk_warning() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate({"usage_percent": 82}) == "warning"


def test_disk_critical() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate({"usage_percent": 91}) == "critical"


def test_memory_warning() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate({"memory_usage": 81}) == "warning"


def test_zombie_warning() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate({"zombie_count": 5}) == "warning"


def test_load_critical() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate({"load_1min": 10.0}) == "critical"


def test_no_threshold_exceeded() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate({"cpu_usage": 50}) is None


def test_evaluate_all() -> None:
    te = ThresholdEvaluator()
    from dataclasses import dataclass

    @dataclass
    class FakePkg:
        success: bool = True
        data: dict | None = None
        evidence_name: str = "CPU"

    pkg = FakePkg(data={"cpu_usage": 92})
    result = te.evaluate_all([pkg])
    assert result == {"CPU": "critical"}


def test_non_dict_skipped() -> None:
    te = ThresholdEvaluator()
    assert te.evaluate("not_a_dict") is None  # type: ignore[arg-type]
