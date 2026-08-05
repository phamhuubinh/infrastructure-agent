from __future__ import annotations

from src.pipeline.composite_rule import CompositeRule, WeightedCondition
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import FindingDecision
from src.pipeline.rule_engine import RuleEngine
from tests.pipeline.reasoning_fact_factory import fact


def _cpu_rule() -> CompositeRule:
    return CompositeRule(
        id="cpu.saturation.test",
        type="cpu_saturation",
        conditions=(
            WeightedCondition("cpu", "cpu.usage", "gt", 80, 0.45),
            WeightedCondition("load", "cpu.load_per_core", "gt", 1, 0.35),
            WeightedCondition(
                "iowait", "cpu.iowait", "gt", 20, 0.20, required=False
            ),
        ),
        decision_threshold=0.8,
        minimum_coverage=0.8,
        severity="critical",
        version="1.0.0",
        owner="qa",
        rationale="test reviewed CPU composite",
        source_cases=("DR1-602",),
    )


def test_cpu_saturation_requires_weight_and_observable_evidence() -> None:
    facts = FactSet(
        (
            fact("cpu.usage", 88.0),
            fact("cpu.load_per_core", 1.5, unit="load_per_core"),
            fact("cpu.iowait", 25.0),
        )
    )

    evaluation = RuleEngine().evaluate_rule(
        _cpu_rule(), facts, target="server-1"
    )

    assert evaluation.finding.decision is FindingDecision.SUPPORTED
    assert evaluation.finding.score == 1.0
    assert evaluation.evidence_coverage == 1.0
    assert len(evaluation.finding.source_links) == 3


def test_observed_false_conditions_are_contradicting() -> None:
    facts = FactSet(
        (
            fact("cpu.usage", 20.0),
            fact("cpu.load_per_core", 0.2, unit="load_per_core"),
            fact("cpu.iowait", 1.0),
        )
    )

    finding = RuleEngine().evaluate_rule(
        _cpu_rule(), facts, target="server-1"
    ).finding

    assert finding.decision is FindingDecision.NOT_SUPPORTED
    assert finding.score == 0.0
    assert len(finding.contradicting_fact_ids) == 3
