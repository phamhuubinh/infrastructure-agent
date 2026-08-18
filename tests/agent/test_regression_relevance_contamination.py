"""Regression matrix for final-answer relevance and cross-request
contamination (#48).

Uses scripted deterministic drafts plus the one-shot repair path so that
semantically unrelated answers can never leak across requests.
"""

from __future__ import annotations

from src.agent.deterministic_agent import DeterministicAgent
from src.model.semantic_planner_adapter import SemanticPlannerAdapter
from tests.fixtures.fake_environment import fake_environment
from tests.fixtures.fake_models import (
    NOT_ALIGNED_CROSS_TASK,
    RecordingEngine,
    ScriptedAssessmentModel,
    ScriptedPlannerProvider,
    capability_plan,
    direct_answer_plan,
    plan_response,
)


def _agent(
    *,
    plan,
    model: ScriptedAssessmentModel,
    engine: RecordingEngine,
    planner_responses,
) -> DeterministicAgent:
    return DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider(list(planner_responses))]
        ),
    )


def test_thanks_cannot_return_a_technical_tutorial() -> None:
    env = fake_environment(localhost=True)
    model = ScriptedAssessmentModel(
        draft="Bạn nên lắp camera và cảm biến cửa để bảo vệ ngôi nhà.",
        verifier_responses=[NOT_ALIGNED_CROSS_TASK, ALIGNED_for_test()],
        repair_response="Không có gì!",
    )
    agent = _agent(
        plan=direct_answer_plan(concept="gratitude acknowledgement"),
        model=model,
        engine=RecordingEngine(env),
        planner_responses=[
            plan_response(direct_answer_plan(concept="gratitude acknowledgement"))
        ],
    )

    result = agent.run_with_steps("Cảm ơn bạn nhé")

    assert result["response"] == "Không có gì!"
    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert semantic["postconditions"]["repair"] == {
        "attempted": True,
        "status": "repaired",
    }


def ALIGNED_for_test() -> str:
    return '{"decision":"aligned","reason":"aligned"}'


def test_sentence_count_shape_is_enforced_and_repaired_once() -> None:
    """A one-sentence draft violates the exact 3-sentence request; one repair
    returning exactly three sentences passes the second verification and
    becomes the final answer."""
    env = fake_environment(localhost=True)
    model = ScriptedAssessmentModel(
        draft="Câu trả lời ngắn đúng ba câu.",  # one sentence — count mismatch
        repair_response=(
            "Tôi là Orion. Tôi có thể hỗ trợ phân tích. "
            "Tôi hoạt động theo các giới hạn an toàn."
        ),
    )
    agent = _agent(
        plan=direct_answer_plan(concept="self introduction"),
        model=model,
        engine=RecordingEngine(env),
        planner_responses=[
            plan_response(direct_answer_plan(concept="self introduction"))
        ],
    )

    result = agent.run_with_steps("Hãy giới thiệu bản thân đúng 3 câu")

    assert result["response"] == (
        "Tôi là Orion. Tôi có thể hỗ trợ phân tích. "
        "Tôi hoạt động theo các giới hạn an toàn."
    )
    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert semantic["postconditions"]["passed"] is True
    assert semantic["postconditions"]["repair"] == {
        "attempted": True,
        "status": "repaired",
    }
    # Exactly one repair call: initial draft, repair, second verification.
    assert [call.kind for call in model.calls] == [
        "response",
        "repair",
        "verifier",
    ]


def test_repaired_draft_still_wrong_sentence_count_is_rejected_not_repaired() -> None:
    """A repair candidate that still violates the exact sentence count must
    fail the second verification: safe deterministic fallback, exactly one
    repair call, no third attempt, and never traced as repaired."""
    env = fake_environment(localhost=True)
    model = ScriptedAssessmentModel(
        draft="Một câu. " * 20,  # twenty sentences — count mismatch
        repair_response="Câu trả lời ngắn đúng ba câu.",  # still one sentence
    )
    agent = _agent(
        plan=direct_answer_plan(concept="self introduction"),
        model=model,
        engine=RecordingEngine(env),
        planner_responses=[
            plan_response(direct_answer_plan(concept="self introduction"))
        ],
    )

    result = agent.run_with_steps("Hãy giới thiệu bản thân đúng 3 câu")

    assert result["response"] == (
        "Câu trả lời bị chặn vì không khớp bằng chứng đã xác thực."
    )
    assert "Câu trả lời ngắn đúng ba câu." != result["response"]
    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert semantic["postconditions"]["passed"] is False
    assert "shape_mismatch" in semantic["postconditions"]["violations"]
    assert semantic["postconditions"]["repair"] == {
        "attempted": True,
        "status": "verification_failed",
    }
    assert [call.kind for call in model.calls].count("repair") == 1
    assert [call.kind for call in model.calls].count("verifier") == 0


def test_retry_policy_review_cannot_return_a_network_assessment() -> None:
    env = fake_environment(localhost=True)
    model = ScriptedAssessmentModel(
        draft="The production server has 32 CPU cores and 128 GB RAM.",
        verifier_responses=[NOT_ALIGNED_CROSS_TASK, ALIGNED_for_test()],
        repair_response="The retry loop stops after three transient failures.",
    )
    agent = _agent(
        plan=direct_answer_plan(concept="HTTP retry review"),
        model=model,
        engine=RecordingEngine(env),
        planner_responses=[
            plan_response(direct_answer_plan(concept="HTTP retry review"))
        ],
    )

    result = agent.run_with_steps("Review the HTTP retry logic.")

    assert result["response"] == "The retry loop stops after three transient failures."
    assert "CPU cores" not in result["response"]


def test_architecture_question_cannot_inject_unrelated_live_evidence() -> None:
    env = fake_environment(localhost=True)
    model = ScriptedAssessmentModel(
        draft="Monitor hiện đang dùng 45% RAM và CPU đạt 90%.",
        verifier_responses=[NOT_ALIGNED_CROSS_TASK, ALIGNED_for_test()],
        repair_response="Kiến trúc microservice tách dịch vụ theo nghiệp vụ.",
    )
    agent = _agent(
        plan=direct_answer_plan(concept="microservice architecture"),
        model=model,
        engine=RecordingEngine(env),
        planner_responses=[
            plan_response(direct_answer_plan(concept="microservice architecture"))
        ],
    )

    result = agent.run_with_steps("Giải thích kiến trúc microservice là gì")

    assert result["response"] == "Kiến trúc microservice tách dịch vụ theo nghiệp vụ."
    assert "45% RAM" not in result["response"]


def test_unrelated_follow_up_does_not_inherit_inspection_content() -> None:
    env = fake_environment(localhost=True)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Generic follow-up answer.")
    planner = ScriptedPlannerProvider(
        [
            plan_response(capability_plan(concept="cpu", target="localhost")),
            plan_response(direct_answer_plan(concept="general answer")),
        ]
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter([planner]),
    )

    agent.run_with_steps("check cpu on localhost")
    second = agent.run_with_steps("What is the capital of France?")

    assert engine.execute_calls == 1
    assert second["response"] == "Generic follow-up answer."
    # The second planner call must not inherit the inspection concept.
    assert "cpu" not in planner.requests[1].user_prompt.casefold()
    # The second response path must not reuse the first inspection context.
    assert second["execution_trace"]["evidence_status"] == "NOT_APPLICABLE"
    assert "France" in planner.requests[1].user_prompt
