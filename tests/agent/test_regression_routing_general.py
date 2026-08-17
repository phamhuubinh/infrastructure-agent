"""Regression matrix for no-tool general/social/meta routing (#44).

Requests that were historically misclassified as infrastructure must stay
on the general/direct path: no target resolution, no evidence collection,
no infrastructure tool calls.
"""

from __future__ import annotations

import pytest

from src.agent.deterministic_agent import DeterministicAgent
from src.model.semantic_planner_adapter import SemanticPlannerAdapter
from tests.fixtures.fake_environment import fake_environment
from tests.fixtures.fake_models import (
    RecordingEngine,
    ScriptedAssessmentModel,
    ScriptedPlannerProvider,
    direct_answer_plan,
    plan_response,
)

GENERAL_REQUESTS = (
    "Cảm ơn bạn nhé",
    "Hãy giới thiệu bản thân trong 2 câu",
    "What can you do besides infrastructure monitoring?",
    "HTTP GET khác POST thế nào?",
    "Zombie process là gì?",
    # Stable explanatory questions that mention infrastructure vocabulary
    # but do not request live inspection.
    "RAM là gì và dùng để làm gì?",
    "What does CPU load average mean?",
    "Giải thích khái niệm uptime trong giám sát hệ thống",
    "Explain what a reverse proxy is",
)


@pytest.mark.parametrize("question", GENERAL_REQUESTS)
def test_general_social_meta_requests_stay_on_the_direct_path(
    question: str,
) -> None:
    env = fake_environment(localhost=True, monitor=True, internet=True)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Câu trả lời chung ngắn gọn.")
    planner = SemanticPlannerAdapter(
        [
            ScriptedPlannerProvider(
                [plan_response(direct_answer_plan(concept="general answer"))]
            )
        ]
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=planner,
    )

    result = agent.run_with_steps(question)

    trace = result["execution_trace"]
    assert engine.execute_calls == 0
    assert engine.frames == []
    assert trace["evidence_status"] == "NOT_APPLICABLE"
    assert trace["routing_status"] == "GENERAL_CHAT"
    assert trace["answer_strategy"] == "CHAT"
    assert result["response"].strip()
    assert [call.kind for call in model.calls].count("response") == 1
