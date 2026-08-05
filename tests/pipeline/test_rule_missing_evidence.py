from __future__ import annotations

from src.pipeline.fact import FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import FindingDecision
from src.pipeline.rule_engine import ConditionState, RuleEngine
from tests.pipeline.reasoning_fact_factory import fact
from tests.pipeline.test_composite_rules import _cpu_rule


def test_missing_required_fact_is_insufficient_without_renormalization() -> None:
    evaluation = RuleEngine().evaluate_rule(
        _cpu_rule(), FactSet((fact("cpu.usage", 95.0),)), target="server-1"
    )

    assert evaluation.finding.decision is FindingDecision.INSUFFICIENT_EVIDENCE
    assert evaluation.finding.score == 0.45
    assert evaluation.finding.maximum_observable_score == 0.45
    assert evaluation.finding.maximum_possible_score == 1.0
    assert evaluation.finding.coverage == 0.45
    assert "cpu.load_per_core" in evaluation.finding.missing_facts


def test_stale_and_failed_are_distinct_condition_states() -> None:
    stale = fact(
        "cpu.load_per_core",
        2.0,
        freshness=FactFreshness.STALE,
        validity=FactValidity.STALE,
        unit="load_per_core",
    )
    failed = fact(
        "cpu.iowait",
        None,
        validity=FactValidity.COMMAND_FAILED,
        unit="unknown",
    )
    evaluation = RuleEngine().evaluate_rule(
        _cpu_rule(),
        FactSet((fact("cpu.usage", 95.0), stale, failed)),
        target="server-1",
    )

    states = {item.metric: item.state for item in evaluation.conditions}
    assert states["cpu.load_per_core"] is ConditionState.STALE
    assert states["cpu.iowait"] is ConditionState.COLLECTION_FAILED
    assert evaluation.finding.decision is FindingDecision.INSUFFICIENT_EVIDENCE
