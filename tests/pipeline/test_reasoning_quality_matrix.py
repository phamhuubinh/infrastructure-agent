"""DR1-805 — reviewed precision/recall scenarios for atomic and composite rules."""

from __future__ import annotations

import pytest

from src.pipeline.composite_rule import CompositeRule, WeightedCondition
from src.pipeline.fact import FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import FindingDecision
from src.pipeline.rule_engine import RuleEngine
from src.pipeline.threshold_evaluator import ThresholdEvaluator
from tests.pipeline.reasoning_fact_factory import fact


def _cpu_saturation_rule() -> CompositeRule:
    return CompositeRule(
        id="cpu.saturation.quality",
        type="cpu_saturation",
        conditions=(
            WeightedCondition("cpu", "cpu.usage", "gt", 80, 0.5),
            WeightedCondition("load", "cpu.load_per_core", "gt", 1, 0.5),
        ),
        decision_threshold=1.0,
        minimum_coverage=1.0,
        severity="critical",
        version="1.0.0",
        owner="qa",
        rationale="Reviewed Epic 8 quality fixture.",
        source_cases=("DR1-805",),
    )


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (
            FactSet((fact("cpu.usage", 91.0), fact("cpu.load_per_core", 1.5))),
            FindingDecision.SUPPORTED,
        ),
        (
            FactSet((fact("cpu.usage", 20.0), fact("cpu.load_per_core", 0.2))),
            FindingDecision.NOT_SUPPORTED,
        ),
        (FactSet((fact("cpu.usage", 91.0),)), FindingDecision.INSUFFICIENT_EVIDENCE),
        (
            FactSet(
                (
                    fact("cpu.usage", 91.0),
                    fact(
                        "cpu.load_per_core",
                        None,
                        validity=FactValidity.STALE,
                        freshness=FactFreshness.STALE,
                        unit="load_per_core",
                    ),
                )
            ),
            FindingDecision.INSUFFICIENT_EVIDENCE,
        ),
        (
            FactSet(
                (
                    fact("cpu.usage", 91.0),
                    fact(
                        "cpu.load_per_core",
                        None,
                        validity=FactValidity.CONTRADICTORY,
                        unit="load_per_core",
                    ),
                )
            ),
            FindingDecision.INSUFFICIENT_EVIDENCE,
        ),
    ],
)
def test_composite_rule_quality_matrix(
    facts: FactSet,
    expected: FindingDecision,
) -> None:
    finding = (
        RuleEngine()
        .evaluate_rule(_cpu_saturation_rule(), facts, target="server-1")
        .finding
    )

    assert finding.id == "finding:cpu.saturation.quality:server-1"
    assert finding.decision is expected


def test_atomic_rule_has_no_false_positive_for_valid_low_utilization() -> None:
    findings = ThresholdEvaluator().evaluate_fact_set(
        FactSet((fact("cpu.usage", 37.0),))
    )

    assert all(
        finding.decision is FindingDecision.NOT_SUPPORTED for finding in findings
    )
    assert not any(
        finding.id.startswith("finding:cpu.usage.warning")
        and finding.decision is FindingDecision.SUPPORTED
        for finding in findings
    )
