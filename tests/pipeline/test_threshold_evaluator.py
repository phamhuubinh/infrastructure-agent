from __future__ import annotations

from src.pipeline.fact import FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import FindingDecision
from src.pipeline.threshold_evaluator import ThresholdEvaluator
from tests.pipeline.reasoning_fact_factory import fact


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


def test_load_threshold_is_per_core_not_absolute() -> None:
    evaluator = ThresholdEvaluator()
    many_core = FactSet(
        (
            fact("system.load_1m", 10.0, unit="load"),
            fact("cpu.logical_cores", 64, unit="count"),
        )
    )
    constrained = FactSet(
        (
            fact("system.load_1m", 10.0, unit="load"),
            fact("cpu.logical_cores", 4, unit="count"),
        )
    )

    assert evaluator.highest_severity(many_core) is None
    assert evaluator.highest_severity(constrained) == "critical"


def test_disk_37_percent_is_not_a_warning() -> None:
    evaluator = ThresholdEvaluator()
    findings = evaluator.evaluate_fact_set(
        FactSet((fact("filesystem.usage", 37.0),))
    )

    assert not any(
        finding.decision is FindingDecision.SUPPORTED for finding in findings
    )


def test_failed_fact_is_never_interpreted_as_a_numeric_zero() -> None:
    evaluator = ThresholdEvaluator()
    findings = evaluator.evaluate_fact_set(
        FactSet(
            (
                fact(
                    "cpu.usage",
                    None,
                    validity=FactValidity.COMMAND_FAILED,
                    unit="unknown",
                ),
            )
        )
    )

    assert findings
    assert all(
        finding.decision is FindingDecision.INSUFFICIENT_EVIDENCE
        for finding in findings
    )
