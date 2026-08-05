from __future__ import annotations

from src.pipeline.evidence_expander import EvidenceExpander, MetricCapability
from src.pipeline.fact_set import FactSet
from src.pipeline.rule_engine import RuleEngine
from tests.pipeline.reasoning_fact_factory import fact
from tests.pipeline.test_composite_rules import _cpu_rule


def test_weighted_selection_is_stable_and_uses_documented_formula() -> None:
    evaluation = RuleEngine().evaluate_rule(
        _cpu_rule(), FactSet((fact("cpu.usage", 95.0),)), target="server-1"
    )
    expander = EvidenceExpander(
        (
            MetricCapability("cpu.load_per_core", "load", "Load", 0.8, 0.2),
            MetricCapability("cpu.iowait", "iowait", "I/O wait", 0.9, 0.3),
        )
    )

    first = expander.select((evaluation,))
    second = expander.select((evaluation,))

    assert first == second
    assert [item.capability for item in first] == ["load", "iowait"]
    assert first[0].priority == 0.35 * 0.8 / 0.2
    assert len(first) <= 2
