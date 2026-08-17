from __future__ import annotations

import pytest

from src.model.semantic_planner_adapter import SemanticPlannerAdapter
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.semantic_plan_wire import (
    SemanticPlanWireError,
    semantic_plan_from_wire,
)
from tests.fixtures.fake_models import (
    ALIGNED,
    NOT_ALIGNED_CROSS_TASK,
    ScriptedAssessmentModel,
    ScriptedPlannerProvider,
    capability_plan,
    direct_answer_plan,
    plan_response,
)

RESPONSE_USAGE = ModelCallUsage(
    input_tokens=10,
    visible_output_tokens=5,
    total_output_tokens=5,
    purpose="response",
)
VERIFIER_USAGE = ModelCallUsage(
    input_tokens=4,
    visible_output_tokens=1,
    total_output_tokens=1,
    purpose="relevance",
)


def test_scripted_model_records_call_kind_prompt_and_usage() -> None:
    model = ScriptedAssessmentModel(
        draft="Không có gì!",
        usages={"response": RESPONSE_USAGE, "verifier": VERIFIER_USAGE},
    )

    assert model.assess(object()) == "Không có gì!"
    assert model.last_usage is RESPONSE_USAGE
    assert model.assess_raw("compact final-answer relevance verifier ...") == ALIGNED
    assert model.last_usage is VERIFIER_USAGE

    kinds = [call.kind for call in model.calls]
    assert kinds == ["response", "verifier"]
    assert model.calls[1].prompt.startswith("compact final-answer relevance verifier")


def test_scripted_model_queues_verifier_verdicts_and_repair_results() -> None:
    model = ScriptedAssessmentModel(
        draft="irrelevant draft",
        verifier_responses=[NOT_ALIGNED_CROSS_TASK, ALIGNED],
        repair_response="Không có gì!",
    )

    first = model.assess_raw("compact final-answer relevance verifier 1")
    second = model.assess_raw("compact final-answer relevance verifier 2")
    repair = model.assess_raw("final-response repairer ...")

    assert first == NOT_ALIGNED_CROSS_TASK
    assert second == ALIGNED
    assert repair == "Không có gì!"
    assert [call.kind for call in model.calls] == [
        "verifier",
        "verifier",
        "repair",
    ]


def test_scripted_model_injects_failures() -> None:
    model = ScriptedAssessmentModel(
        repair_error=RuntimeError("down"),
        assess_error=ConnectionError("provider offline"),
    )

    with pytest.raises(RuntimeError, match="down"):
        model.assess_raw("final-response repairer ...")
    with pytest.raises(ConnectionError):
        model.assess(object())


def test_scripted_planner_provider_queues_responses_and_captures_requests() -> None:
    plan = direct_answer_plan(concept="greeting")
    provider = ScriptedPlannerProvider(
        [
            plan_response(plan, raw_usage={"prompt_tokens": 3, "completion_tokens": 2}),
        ]
    )
    adapter = SemanticPlannerAdapter([provider])

    result = adapter.plan("hello")

    assert result.plan == plan
    assert result.raw_usage == {"prompt_tokens": 3, "completion_tokens": 2}
    assert provider.requests[0].purpose.value == "planner"
    assert "hello" in provider.requests[0].user_prompt

    with pytest.raises(RuntimeError, match="script exhausted"):
        adapter.plan("hello again")


def test_scripted_planner_provider_raises_scripted_errors() -> None:
    provider = ScriptedPlannerProvider([RuntimeError("provider down")])
    adapter = SemanticPlannerAdapter([provider])

    outcome = adapter.plan_safely("hello")

    assert outcome.status.value == "failed"
    assert outcome.reason.value == "provider_error"


def test_plan_response_accepts_malformed_payloads_for_rejection_tests() -> None:
    malformed = plan_response({"r": "DIRECT_ANSWER", "extra_authority": "root"})
    with pytest.raises(SemanticPlanWireError):
        semantic_plan_from_wire(malformed.payload)


def test_plan_builders_round_trip_through_the_wire_contract() -> None:
    direct = direct_answer_plan(concept="gratitude acknowledgement")
    capability = capability_plan(
        concept="cpu",
        target="localhost",
        sources=(SourceConstraint_of_test(),),
    )

    assert semantic_plan_from_wire(plan_response(direct).payload) == direct
    assert semantic_plan_from_wire(plan_response(capability).payload) == capability


def SourceConstraint_of_test():
    from src.pipeline.request_semantics import SourceConstraint

    return SourceConstraint.ANY
