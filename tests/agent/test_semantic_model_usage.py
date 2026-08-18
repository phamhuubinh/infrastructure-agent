from __future__ import annotations

import json

from src.agent.deterministic_agent import DeterministicAgent
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.semantic_planner_adapter import (
    PlannerProviderRequest,
    PlannerProviderResponse,
    SemanticPlannerAdapter,
)
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.execution_runtime import RuntimeMetrics
from src.pipeline.investigation_request import InvestigationRequest
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
    TargetReference,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_wire import semantic_plan_to_wire
from src.pipeline.target_resolver import TargetResolver
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry

RESPONSE_USAGE = ModelCallUsage(
    input_tokens=120,
    reasoning_tokens=80,
    visible_output_tokens=40,
    total_output_tokens=120,
    model="fake-model",
    provider="fake",
    latency_ms=10.0,
)
RELEVANCE_USAGE = ModelCallUsage(
    input_tokens=20,
    reasoning_tokens=0,
    visible_output_tokens=10,
    total_output_tokens=10,
    model="fake-model",
    provider="fake",
    latency_ms=2.0,
)
REPAIR_USAGE = ModelCallUsage(
    input_tokens=30,
    reasoning_tokens=None,
    visible_output_tokens=12,
    total_output_tokens=12,
    model="fake-model",
    provider="fake",
    latency_ms=3.0,
)


class UsageScenarioModel(AssessmentModelAdapter):
    """Deterministic fake that reports normalized usage after each call."""

    def __init__(
        self,
        draft: str,
        *,
        verifier_responses: list[str] | None = None,
        repair_response: str | None = None,
    ) -> None:
        self.draft = draft
        self.verifier_responses = verifier_responses or [
            '{"decision":"aligned","reason":"aligned"}'
        ]
        self.repair_response = repair_response or draft
        self._last_usage: ModelCallUsage | None = None

    @property
    def last_usage(self) -> ModelCallUsage | None:
        return self._last_usage

    def assess(self, _request: AssessmentRequest) -> str:
        self._last_usage = RESPONSE_USAGE
        return self.draft

    def assess_raw(self, prompt: str) -> str:
        if "compact final-answer relevance verifier" in prompt:
            self._last_usage = RELEVANCE_USAGE
            if len(self.verifier_responses) > 1:
                return self.verifier_responses.pop(0)
            return self.verifier_responses[0]
        if "final-response repairer" in prompt:
            self._last_usage = REPAIR_USAGE
            return self.repair_response
        self._last_usage = RESPONSE_USAGE
        return self.draft


class UsagePlannerProvider:
    def __init__(self, plan: SemanticPlan) -> None:
        self.plan = plan

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        return PlannerProviderResponse(
            payload=semantic_plan_to_wire(self.plan),
            provider="test",
            model="semantic-test",
            raw_usage={
                "prompt_tokens": 11,
                "completion_tokens": 12,
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
        )


class UsageExecutionEngine:
    """Fake engine for capability-assisted loops; never touches tools."""

    def __init__(self) -> None:
        registry = TargetRegistry()
        registry.add("localhost")
        self.knowledge_tool = KnowledgeTool(registry)
        self.target_resolver = TargetResolver(registry)
        self.execution_budget_config = None
        self.execute_calls = 0

    def execute(self, frame) -> InvestigationRequest:
        self.execute_calls += 1
        return InvestigationRequest(
            raw_request=frame.raw_request,
            target=frame.target_resolved,
            request_frame=frame,
            runtime_metrics=RuntimeMetrics(tool_calls=1),
            evidence_complete=True,
        )


def _direct_plan() -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        concept="greeting",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _capability_plan() -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.ENVIRONMENT,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        target=TargetReference(TargetReferenceKind.EXPLICIT, "localhost"),
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.CURRENT,
        concept="cpu",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _agent(
    plan: SemanticPlan,
    model: UsageScenarioModel,
    engine: UsageExecutionEngine,
) -> DeterministicAgent:
    return DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter([UsagePlannerProvider(plan)]),
    )


def _model_usage(result: dict) -> dict:
    return result["execution_trace"]["runtime_metrics"]["model_usage"]


def test_direct_answer_records_planner_response_and_relevance_usage() -> None:
    model = UsageScenarioModel("Xin chào!")
    agent = _agent(_direct_plan(), model, UsageExecutionEngine())

    result = agent.run_with_steps("Xin chào")

    usage = _model_usage(result)
    assert usage["calls"] == 3
    assert usage["dropped_calls"] == 0
    planner_usage = usage["by_purpose"]["planner"]
    assert planner_usage == {
        "calls": 1,
        "latency_ms": planner_usage["latency_ms"],
        "input_tokens": 11,
        "reasoning_tokens": 3,
        "visible_output_tokens": 9,
        "total_output_tokens": 12,
        "estimated_input_tokens": planner_usage["estimated_input_tokens"],
    }
    assert planner_usage["latency_ms"] is not None
    # The provider-neutral planner estimate is recorded separately from the
    # provider-reported input tokens (11) and is never substituted for it.
    planner_estimate = planner_usage["estimated_input_tokens"]
    assert isinstance(planner_estimate, int)
    assert planner_estimate > 11
    assert usage["by_purpose"]["response"] == {
        "calls": 1,
        "latency_ms": 10.0,
        "input_tokens": 120,
        "reasoning_tokens": 80,
        "visible_output_tokens": 40,
        "total_output_tokens": 120,
        "estimated_input_tokens": (
            usage["by_purpose"]["response"]["estimated_input_tokens"]
        ),
    }
    response_estimate = usage["by_purpose"]["response"]["estimated_input_tokens"]
    assert isinstance(response_estimate, int)
    assert response_estimate > 0
    assert response_estimate != 120
    assert usage["by_purpose"]["relevance"] == {
        "calls": 1,
        "latency_ms": 2.0,
        "input_tokens": 20,
        "reasoning_tokens": 0,
        "visible_output_tokens": 10,
        "total_output_tokens": 10,
        "estimated_input_tokens": None,
    }
    per_call = usage["per_call"]
    assert [entry["purpose"] for entry in per_call] == [
        "response",
        "relevance",
        "planner",
    ]
    for entry in per_call:
        assert set(entry) == {
            "input_tokens",
            "reasoning_tokens",
            "visible_output_tokens",
            "total_output_tokens",
            "model",
            "provider",
            "purpose",
            "latency_ms",
            "estimated_input_tokens",
            "configured_effort",
        }
    planner_entry = next(entry for entry in per_call if entry["purpose"] == "planner")
    assert planner_entry["input_tokens"] == 11
    assert planner_entry["estimated_input_tokens"] == planner_estimate
    assert planner_entry["estimated_input_tokens"] != planner_entry["input_tokens"]
    json.dumps(usage)


def test_tool_assisted_request_records_assessment_usage() -> None:
    model = UsageScenarioModel("Bounded assessment.")
    engine = UsageExecutionEngine()
    agent = _agent(_capability_plan(), model, engine)

    result = agent.run_with_steps("check cpu on localhost")

    assert engine.execute_calls == 1
    usage = _model_usage(result)
    assert usage["calls"] == 3
    assert usage["by_purpose"]["response"]["calls"] == 1
    assert usage["by_purpose"]["relevance"]["calls"] == 1
    assert usage["by_purpose"]["planner"]["calls"] == 1
    json.dumps(result["execution_trace"])


def test_repair_call_usage_is_recorded_with_repair_purpose() -> None:
    model = UsageScenarioModel(
        "You should install cameras and sensors for your house.",
        verifier_responses=[
            '{"decision":"not_aligned","reason":"cross_task"}',
            '{"decision":"aligned","reason":"aligned"}',
        ],
        repair_response="Không có gì!",
    )
    agent = _agent(_direct_plan(), model, UsageExecutionEngine())

    result = agent.run_with_steps("Cảm ơn bạn nhé")

    usage = _model_usage(result)
    assert usage["calls"] == 5
    assert usage["by_purpose"]["relevance"]["calls"] == 2
    assert usage["by_purpose"]["relevance"]["input_tokens"] == 40
    assert usage["by_purpose"]["repair"] == {
        "calls": 1,
        "latency_ms": 3.0,
        "input_tokens": 30,
        "reasoning_tokens": None,
        "visible_output_tokens": 12,
        "total_output_tokens": 12,
        "estimated_input_tokens": None,
    }
    assert result["response"] == "Không có gì!"
