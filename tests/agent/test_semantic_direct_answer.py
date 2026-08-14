from __future__ import annotations

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
        return "Câu trả lời trực tiếp."


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
