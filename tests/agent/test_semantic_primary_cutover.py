"""Semantic-primary cutover regressions (#52).

With a semantic planner configured, the bounded semantic loop is the sole
authority for intent on the primary request path. Planner failure,
malformed planner output, and every other non-success loop outcome must
terminate as bounded semantic-loop failures — the legacy regex-first
``_route_request`` path must never be consulted as a fallback, even for
requests it would route straight into the environment pipeline.
"""

from __future__ import annotations

from src.agent.deterministic_agent import DeterministicAgent
from src.model.semantic_planner_adapter import SemanticPlannerAdapter
from tests.fixtures.fake_environment import fake_environment
from tests.fixtures.fake_models import (
    RecordingEngine,
    ScriptedAssessmentModel,
    ScriptedPlannerProvider,
    plan_response,
)

INFRA_REQUEST = "Check CPU usage on localhost"


def _planner_agent(
    planner_responses: list,
) -> tuple[DeterministicAgent, RecordingEngine, ScriptedAssessmentModel]:
    env = fake_environment(localhost=True, monitor=True, internet=True)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Câu trả lời chung ngắn gọn.")
    planner = SemanticPlannerAdapter([ScriptedPlannerProvider(list(planner_responses))])
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=planner,
    )
    return agent, engine, model


def test_planner_provider_failure_never_falls_back_to_legacy_routing() -> None:
    """A planner provider failure on an environment request terminates as
    a bounded semantic-loop failure: zero legacy routing, zero execution,
    zero model calls."""
    agent, engine, model = _planner_agent([RuntimeError("provider down")])

    result = agent.run_with_steps(INFRA_REQUEST)

    assert engine.execute_calls == 0
    assert engine.frames == []
    assert model.calls == []
    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert semantic["terminal_state"] == "FAIL"
    assert semantic["failure"] == "provider_failure"
    assert result["execution_trace"]["routing_status"] == "UNSUPPORTED"
    assert result["response"].strip()


def test_malformed_planner_output_never_falls_back_to_legacy_routing() -> None:
    """A malformed planner payload on an environment request stops at the
    bounded loop — the legacy environment pipeline is never dispatched."""
    agent, engine, _model = _planner_agent([plan_response(None)])

    result = agent.run_with_steps(INFRA_REQUEST)

    assert engine.execute_calls == 0
    assert engine.frames == []
    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert semantic["terminal_state"] == "FAIL"
    assert semantic["failure"] == "provider_failure"


def test_planner_failure_terminates_the_run_text_path_too() -> None:
    """The plain ``run()`` primary path applies the same cutover: the
    bounded failure text is returned, never a legacy-routed answer."""
    agent, engine, _model = _planner_agent([RuntimeError("provider down")])

    response = agent.run(INFRA_REQUEST)

    assert engine.execute_calls == 0
    assert (
        "no additional tools were run" in response
        or "không chạy thêm công cụ" in response
    )


def test_legacy_path_still_serves_the_same_request_without_a_planner() -> None:
    """Compatibility mode: with no planner the same request still routes
    through the legacy deterministic path and executes — proving the
    cutover scenarios above are ones where a legacy fallback would have
    been observable as an engine dispatch."""
    env = fake_environment(localhost=True, monitor=True, internet=True)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Câu trả lời chung ngắn gọn.")
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
    )

    result = agent.run_with_steps(INFRA_REQUEST)

    assert engine.execute_calls == 1
    assert result["response"].strip()
