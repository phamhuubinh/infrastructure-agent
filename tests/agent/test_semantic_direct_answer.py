from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.agent.conversation_store import ConversationStore
from src.agent.deterministic_agent import DeterministicAgent
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.semantic_planner_adapter import (
    PlannerProviderRequest,
    PlannerProviderResponse,
    SemanticPlannerAdapter,
)
from src.model.semantic_response_repairer import (
    SemanticRepairResult,
    SemanticRepairStatus,
)
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
)
from src.pipeline.semantic_plan_wire import semantic_plan_to_wire
from src.pipeline.target_resolver import TargetResolver
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


class CapturingAssessmentModel(AssessmentModelAdapter):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def assess(self, assessment_request: AssessmentRequest) -> str:
        return "ok"

    def assess_raw(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "compact final-answer relevance verifier" in prompt:
            return '{"decision":"aligned","reason":"aligned"}'
        return "Câu trả lời trực tiếp."


class RelevanceScenarioModel(AssessmentModelAdapter):
    def __init__(
        self,
        draft: str,
        verifier_response: str | list[str],
        repair_response: str | None = None,
        repair_error: Exception | None = None,
    ) -> None:
        self.draft = draft
        self.verifier_responses = (
            list(verifier_response)
            if isinstance(verifier_response, list)
            else [verifier_response]
        )
        self.repair_response = repair_response if repair_response is not None else draft
        self.repair_error = repair_error
        self.prompts: list[str] = []

    def assess(self, _assessment_request: AssessmentRequest) -> str:
        return self.draft

    def assess_raw(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "compact final-answer relevance verifier" in prompt:
            if len(self.verifier_responses) > 1:
                return self.verifier_responses.pop(0)
            return self.verifier_responses[0]
        if "final-response repairer" in prompt:
            if self.repair_error is not None:
                raise self.repair_error
            return self.repair_response
        return self.draft


class FixedPlannerProvider:
    def __init__(self, plan: SemanticPlan) -> None:
        self.plan = plan
        self.requests: list[PlannerProviderRequest] = []

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        self.requests.append(request)
        return PlannerProviderResponse(
            payload=semantic_plan_to_wire(self.plan),
            provider="test",
            model="semantic-test",
        )


class NoExecutionEngine:
    def __init__(self) -> None:
        registry = TargetRegistry()
        registry.add("localhost")
        self.knowledge_tool = KnowledgeTool(registry)
        self.target_resolver = TargetResolver(registry)
        self.execute_calls = 0

    def execute(self, request_frame):
        self.execute_calls += 1
        raise AssertionError("direct-answer path must not execute infrastructure")


def _direct_plan() -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        concept="general answer",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _agent(
    plan: SemanticPlan,
    *,
    store: ConversationStore | None = None,
) -> tuple[DeterministicAgent, NoExecutionEngine, CapturingAssessmentModel]:
    engine = NoExecutionEngine()
    model = CapturingAssessmentModel()
    planner = SemanticPlannerAdapter([FixedPlannerProvider(plan)])
    return (
        DeterministicAgent(
            engine,  # type: ignore[arg-type]
            model,
            conversation_store=store,
            semantic_planner=planner,
        ),
        engine,
        model,
    )


def _scenario_agent(
    request_concept: str,
    draft: str,
    verifier_response: str | list[str],
    repair_response: str | None = None,
    repair_error: Exception | None = None,
) -> tuple[DeterministicAgent, RelevanceScenarioModel]:
    engine = NoExecutionEngine()
    model = RelevanceScenarioModel(
        draft,
        verifier_response,
        repair_response,
        repair_error,
    )
    plan = replace(_direct_plan(), concept=request_concept)
    return (
        DeterministicAgent(
            engine,  # type: ignore[arg-type]
            model,
            semantic_planner=SemanticPlannerAdapter([FixedPlannerProvider(plan)]),
        ),
        model,
    )


@pytest.mark.parametrize(
    "user_text",
    (
        "hello",
        "Cảm ơn bạn nhé",
        "Explain GET versus POST",
        "Dịch 'good morning' sang tiếng Việt",
        "Write a short paragraph about rain",
        "Write a Python function that adds two integers",
    ),
)
def test_validated_direct_answers_make_zero_infrastructure_calls(
    user_text: str,
) -> None:
    agent, engine, model = _agent(_direct_plan())

    result = agent.run_with_steps(user_text)

    assert result["response"]
    assert result["steps"] == []
    assert result["investigation"] is None
    assert result["execution_trace"]["evidence_status"] == "NOT_APPLICABLE"
    assert engine.execute_calls == 0
    assert user_text in model.prompts[-1]


@pytest.mark.parametrize(
    ("user_request", "concept", "draft", "reason", "blocked_marker"),
    (
        (
            "Cảm ơn bạn nhé",
            "gratitude acknowledgement",
            "Bạn nên lắp camera và cảm biến cửa để bảo vệ ngôi nhà.",
            "cross_task",
            "bị chặn",
        ),
        (
            "Review the HTTP retry logic.",
            "HTTP retry review",
            "The production server has 32 CPU cores and 128 GB RAM.",
            "request_not_answered",
            "blocked",
        ),
    ),
)
def test_semantic_relevance_rejects_otherwise_valid_cross_task_drafts(
    user_request: str,
    concept: str,
    draft: str,
    reason: str,
    blocked_marker: str,
) -> None:
    agent, model = _scenario_agent(
        concept,
        draft,
        json.dumps({"decision": "not_aligned", "reason": reason}),
    )

    result = agent.run_with_steps(user_request)

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert blocked_marker in result["response"]
    assert draft not in result["response"]
    assert semantic["postconditions"]["relevance"] == {
        "decision": "not_aligned",
        "reason": reason,
    }
    assert semantic["postconditions"]["violations"] == ["semantic_not_aligned"]
    # The repair candidate (the same irrelevant draft) failed the second
    # verification, so it must never be traced as repaired.
    assert semantic["postconditions"]["repair"] == {
        "attempted": True,
        "status": "verification_failed",
    }
    assert len(model.prompts) == 4
    assert "analysis" not in json.dumps(semantic)


def test_single_repair_can_restore_an_irrelevant_direct_answer() -> None:
    agent, model = _scenario_agent(
        "gratitude acknowledgement",
        "You should install cameras and sensors for your house.",
        [
            '{"decision":"not_aligned","reason":"cross_task"}',
            '{"decision":"aligned","reason":"aligned"}',
        ],
        repair_response="Không có gì!",
    )

    result = agent.run_with_steps("Cảm ơn bạn nhé")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert result["response"] == "Không có gì!"
    assert semantic["postconditions"] == {
        "passed": True,
        "violations": [],
        "relevance": {"decision": "aligned", "reason": "aligned"},
        "repair": {"attempted": True, "status": "repaired"},
    }
    assert len(model.prompts) == 4


@pytest.mark.parametrize(
    ("repair_response", "repair_error", "expected_status", "prompt_count"),
    (
        (" \n", None, "empty_response", 3),
        (None, RuntimeError("provider down"), "provider_unavailable", 3),
    ),
)
def test_failed_repair_terminates_with_safe_fallback(
    repair_response: str | None,
    repair_error: Exception | None,
    expected_status: str,
    prompt_count: int,
) -> None:
    agent, model = _scenario_agent(
        "gratitude acknowledgement",
        "You should install cameras and sensors for your house.",
        '{"decision":"not_aligned","reason":"cross_task"}',
        repair_response=repair_response,
        repair_error=repair_error,
    )

    result = agent.run_with_steps("Cảm ơn bạn nhé")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert "bị chặn" in result["response"]
    assert semantic["postconditions"]["passed"] is False
    assert semantic["postconditions"]["repair"] == {
        "attempted": True,
        "status": expected_status,
    }
    assert len(model.prompts) == prompt_count


@pytest.mark.parametrize(
    ("user_request", "concept", "draft"),
    (
        ("Cảm ơn bạn nhé", "gratitude acknowledgement", "Không có gì!"),
        (
            "Review the HTTP retry logic.",
            "HTTP retry review",
            "The retry loop stops after three transient failures.",
        ),
    ),
)
def test_semantic_relevance_keeps_correct_concise_drafts(
    user_request: str,
    concept: str,
    draft: str,
) -> None:
    agent, _model = _scenario_agent(
        concept,
        draft,
        '{"decision":"aligned","reason":"aligned"}',
    )

    result = agent.run_with_steps(user_request)

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert result["response"] == draft
    assert semantic["postconditions"]["relevance"] == {
        "decision": "aligned",
        "reason": "aligned",
    }
    assert semantic["postconditions"]["passed"] is True


class _InputRejectedRepairer:
    """Mimics the repair boundary rejecting an unacceptable repair input
    (e.g. an oversized original request) without ever calling a model."""

    def repair(self, original_request, *, violations, relevance_reason, facts):
        return SemanticRepairResult(SemanticRepairStatus.INPUT_REJECTED)


def test_oversized_original_request_fails_safely_at_the_loop_boundary() -> None:
    """A >4096-character request is rejected at the bounded loop boundary
    with a deterministic message — never a generic RESPONSE_FAILED and never
    a model call."""
    long_request = "Cảm ơn bạn nhé " + "xem " * 1200  # well over 4096 chars
    agent, model = _scenario_agent(
        "gratitude acknowledgement",
        "You should install cameras and sensors for your house.",
        '{"decision":"not_aligned","reason":"cross_task"}',
    )

    result = agent.run_with_steps(long_request)

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert semantic["terminal_state"] == "FAIL"
    assert semantic["failure"] == "provider_failure"
    assert "đã dừng" in result["response"]
    assert model.prompts == []


def test_rejected_repair_input_fails_safely_without_loop_failure() -> None:
    """GA2-C09: when the repair boundary rejects its input, the loop keeps
    the deterministic guard fallback, traces input_rejected, and never
    degrades into a generic RESPONSE_FAILED."""
    engine = NoExecutionEngine()
    model = RelevanceScenarioModel(
        "You should install cameras and sensors for your house.",
        '{"decision":"not_aligned","reason":"cross_task"}',
    )
    plan = replace(_direct_plan(), concept="gratitude acknowledgement")
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter([FixedPlannerProvider(plan)]),
        semantic_response_repairer=_InputRejectedRepairer(),
    )

    result = agent.run_with_steps("Cảm ơn bạn nhé")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert semantic["terminal_state"] == "DONE"
    assert semantic["failure"] is None
    assert "bị chặn" in result["response"]
    assert semantic["postconditions"]["repair"] == {
        "attempted": True,
        "status": "input_rejected",
    }
    # Only the chat response and the relevance verifier called the model;
    # the repairer never received a model call.
    assert len(model.prompts) == 2


def test_valid_direct_answer_does_not_enter_infrastructure_discovery(
    monkeypatch,
) -> None:
    agent, engine, _model = _agent(_direct_plan())

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("target resolution must be skipped")

    monkeypatch.setattr(
        engine.target_resolver,
        "validate_semantic_target",
        fail_if_called,
    )
    monkeypatch.setattr(
        engine.knowledge_tool,
        "source_names",
        fail_if_called,
    )

    response = agent.run("hello")

    assert response
    assert engine.execute_calls == 0


def test_direct_answer_uses_only_bounded_relevant_context(tmp_path) -> None:
    store = ConversationStore("semantic-direct", store_dir=str(tmp_path))
    store.add_turn("old request", "SECRET_OLD_EVIDENCE")
    agent, engine, model = _agent(_direct_plan(), store=store)

    agent.run("Explain GET versus POST")

    assert engine.execute_calls == 0
    assert "SECRET_OLD_EVIDENCE" not in model.prompts[-1]
    assert "Explain GET versus POST" in model.prompts[-1]


def test_mutation_cannot_use_direct_answer_even_if_planner_downgrades_it() -> None:
    agent, engine, model = _agent(_direct_plan())

    response = agent.run("restart nginx")

    assert response
    assert engine.execute_calls == 0
    assert model.prompts == []


def test_live_information_cannot_use_model_memory_directly() -> None:
    plan = replace(
        _direct_plan(),
        domain=RequestDomain.EXTERNAL_INFORMATION,
        freshness=FreshnessRequirement.CURRENT,
    )
    agent, engine, model = _agent(plan)

    response = agent.run("Who is the current holder of this office?")

    assert response
    assert engine.execute_calls == 0
    assert model.prompts == []
