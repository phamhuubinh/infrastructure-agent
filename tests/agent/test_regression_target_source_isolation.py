"""Target/source isolation regression matrix (#47).

Asserts both dispatch decisions and the resulting target/provenance
metadata so leaks between targets or sources cannot regress silently.
"""

from __future__ import annotations

from dataclasses import replace

from src.agent.deterministic_agent import DeterministicAgent
from src.model.semantic_planner_adapter import SemanticPlannerAdapter
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet
from src.pipeline.provenance import Provenance
from src.pipeline.request_semantics import (
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    TargetReferenceKind,
)
from tests.fixtures.fake_environment import fake_environment
from tests.fixtures.fake_models import (
    RecordingEngine,
    ScriptedAssessmentModel,
    ScriptedPlannerProvider,
    capability_plan,
    plan_response,
)


def _agent(engine, model, plans) -> DeterministicAgent:
    return DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan) for plan in plans])]
        ),
    )


def _facts_for_target(target: str) -> FactSet:
    fact = Fact(
        subject="web",
        metric="memory.used_bytes",
        value=4096,
        unit="bytes",
        observed_at="2026-08-14T00:00:00Z",  # type: ignore[arg-type]
        collected_at="2026-08-14T00:00:00Z",  # type: ignore[arg-type]
        source="linux",
        target=target,
        validity=FactValidity.VALID,
        freshness=FactFreshness.FRESH,
        confidence=1.0,
        provenance=Provenance(
            source="linux",
            capability="linux.memory",
            target=target,
            source_reference=f"run-{target}",
        ),
    )
    return FactSet((fact,))


def test_explicit_unknown_target_clarifies_without_localhost_fallback() -> None:
    env = fake_environment(localhost=True)
    engine = RecordingEngine(env)
    agent = _agent(
        engine,
        ScriptedAssessmentModel(draft="ignored"),
        [capability_plan(concept="cpu", target="ghost-host")],
    )

    result = agent.run_with_steps("check cpu on ghost-host")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert engine.execute_calls == 0
    assert semantic["terminal_state"] == "FAIL"
    assert semantic["failure"] == "validation_failed"
    assert semantic["failure_detail"] == "target_unknown"


def test_monitor_follow_up_inherits_monitor_target() -> None:
    env = fake_environment(localhost=True, monitor=True)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Read-only assessment.")
    plans = [
        capability_plan(concept="cpu", target="monitor"),
        capability_plan(
            concept="memory",
            target="monitor",
            target_kind=TargetReferenceKind.INHERITED,
        ),
    ]
    agent = _agent(engine, model, plans)

    agent.run_with_steps("check cpu on monitor")
    agent.run_with_steps("RAM thế nào?")

    assert engine.execute_calls == 2
    assert engine.frames[0].target_resolved == "monitor"
    assert engine.frames[1].target_resolved == "monitor"


def test_explicit_target_switch_overrides_inherited_target() -> None:
    env = fake_environment(localhost=True, monitor=True)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Read-only assessment.")
    plans = [
        capability_plan(concept="cpu", target="monitor"),
        capability_plan(concept="memory", target="localhost"),
        capability_plan(concept="cpu", target="monitor"),
    ]
    agent = _agent(engine, model, plans)

    agent.run_with_steps("check cpu on monitor")
    agent.run_with_steps("check memory on localhost")
    agent.run_with_steps("check cpu lại trên monitor")

    assert [frame.target_resolved for frame in engine.frames] == [
        "monitor",
        "localhost",
        "monitor",
    ]


def test_constrained_grafana_source_validates_only_when_available() -> None:
    available_env = fake_environment(localhost=True, monitor=True, grafana=True)
    available_engine = RecordingEngine(available_env)
    available_agent = _agent(
        available_engine,
        ScriptedAssessmentModel(draft="Read-only assessment."),
        [
            capability_plan(
                concept="grafana dashboards",
                target="monitor",
                sources=(SourceConstraint.GRAFANA,),
            )
        ],
    )
    missing_env = fake_environment(localhost=True, monitor=True)
    missing_engine = RecordingEngine(missing_env)
    missing_agent = _agent(
        missing_engine,
        ScriptedAssessmentModel(draft="Read-only assessment."),
        [
            capability_plan(
                concept="grafana dashboards",
                target="monitor",
                sources=(SourceConstraint.GRAFANA,),
            )
        ],
    )

    available_result = available_agent.run_with_steps(
        "list grafana dashboards"
    )
    missing_result = missing_agent.run_with_steps("list grafana dashboards")

    available_semantic = available_result["execution_trace"]["runtime_metrics"][
        "semantic_loop"
    ]
    missing_semantic = missing_result["execution_trace"]["runtime_metrics"][
        "semantic_loop"
    ]
    # With grafana registered the constraint validates; binding fails closed
    # only for evidence the constrained source cannot serve — and never
    # falls back to another source.
    assert available_semantic["validation"]["status"] == "valid"
    assert available_semantic["validation"]["allowed_sources"] == ["grafana"]
    assert available_engine.execute_calls == 0
    assert available_semantic["failure"] == "binding_failed"
    # Without grafana the constraint itself is rejected before binding.
    assert missing_engine.execute_calls == 0
    assert missing_semantic["terminal_state"] == "FAIL"
    assert missing_semantic["failure"] == "validation_failed"


def test_unavailable_constrained_source_never_falls_back_to_any() -> None:
    env = fake_environment(localhost=True, grafana=True)  # no zabbix
    engine = RecordingEngine(env)
    agent = _agent(
        engine,
        ScriptedAssessmentModel(draft="ignored"),
        [
            capability_plan(
                concept="zabbix hosts",
                target="monitor",
                sources=(SourceConstraint.ZABBIX,),
            )
        ],
    )

    result = agent.run_with_steps("list zabbix hosts")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert engine.execute_calls == 0
    assert semantic["failure"] == "validation_failed"


def test_source_exclusion_is_enforced_before_dispatch() -> None:
    env = fake_environment(localhost=True, monitor=True, grafana=True, zabbix=True)
    engine = RecordingEngine(env)
    agent = _agent(
        engine,
        ScriptedAssessmentModel(draft="ignored"),
        [
            capability_plan(
                concept="grafana dashboards",
                target="monitor",
                sources=(SourceConstraint.ANY,),
                excluded_sources=(SourceConstraint.GRAFANA,),
            )
        ],
    )

    result = agent.run_with_steps("list dashboards but not from grafana")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert engine.execute_calls == 1
    values = semantic["validation"]["values"]
    allowed = next(
        str(item["normalized"])
        for item in values
        if item["field"] == "source.allowed"
    )
    excluded = next(
        str(item["normalized"])
        for item in values
        if item["field"] == "source.excluded"
    )
    assert excluded == "grafana"
    assert "grafana" not in allowed
    assert "zabbix" in allowed or "localhost" in allowed


def test_two_target_comparison_keeps_provenance_separate() -> None:
    env = fake_environment(localhost=True, monitor=True)
    engine = RecordingEngine(env)
    original_execute = engine.execute

    def execute_with_facts(frame):
        investigation = original_execute(frame)
        return replace(
            investigation,
            fact_set=_facts_for_target(frame.target_resolved or "localhost"),
        )

    engine.execute = execute_with_facts  # type: ignore[method-assign]
    model = ScriptedAssessmentModel(draft="Read-only assessment.")
    plans = [
        capability_plan(concept="memory", target="monitor"),
        capability_plan(concept="memory", target="localhost"),
    ]
    agent = _agent(engine, model, plans)

    agent.run_with_steps("RAM trên monitor")
    agent.run_with_steps("RAM trên localhost")

    assert engine.execute_calls == 2
    assessment_facts = [
        call.prompt for call in model.calls if call.kind == "response"
    ]
    assert len(assessment_facts) == 2
    first_facts = assessment_facts[0]
    second_facts = assessment_facts[1]
    assert first_facts.startswith("RAM trên monitor")
    assert second_facts.startswith("RAM trên localhost")
