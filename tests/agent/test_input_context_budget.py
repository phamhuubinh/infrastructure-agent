from __future__ import annotations

import pytest

from src.agent.deterministic_agent import DeterministicAgent
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.protocol.semantic_planner_prompt import PlannerPromptContext
from src.model.semantic_planner_adapter import (
    PlannerProviderRequest,
    PlannerProviderResponse,
    SemanticPlannerAdapter,
)
from src.model.semantic_relevance_verifier import (
    SemanticRelevanceDecision,
    SemanticRelevanceReason,
    SemanticRelevanceResult,
)
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.input_context_budget import (
    InputContextBudget,
    InputContextBudgetClass,
    InputContextBudgetError,
    InputContextBudgetPolicy,
)
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
from src.pipeline.semantic_plan_wire import planner_output_to_wire
from src.pipeline.target_resolver import TargetResolver
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


class NoModelCalls(AssessmentModelAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def assess(self, _request: AssessmentRequest) -> str:
        self.calls += 1
        raise AssertionError("single-call path must not call the response model")

    def assess_raw(self, _prompt: str) -> str:
        self.calls += 1
        raise AssertionError("single-call path must not call the response model")


class PassingRelevanceVerifier:
    """Deterministic verifier for a test focused on planner input size."""

    def verify(
        self,
        _original_request: str,
        _plan: SemanticPlan,
        _draft: str,
    ) -> SemanticRelevanceResult:
        return SemanticRelevanceResult(
            SemanticRelevanceDecision.ALIGNED,
            SemanticRelevanceReason.ALIGNED,
        )


class CapturingPlannerProvider:
    def __init__(self, plan: SemanticPlan, final_answer: str) -> None:
        self.plan = plan
        self.final_answer = final_answer
        self.requests: list[PlannerProviderRequest] = []

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        self.requests.append(request)
        return PlannerProviderResponse(
            payload=planner_output_to_wire(self.plan, self.final_answer),
            provider="test",
            model="semantic-test",
            raw_usage={
                "prompt_tokens": 11,
                "completion_tokens": 12,
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
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
        raise AssertionError("no-tool path must not execute infrastructure")


class CapturingModel(AssessmentModelAdapter):
    """Response model that records the prompts handed to it."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def assess(self, _request: AssessmentRequest) -> str:
        return "assessed"

    def assess_raw(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ok"


class OversizedStore:
    """Conversation store stuffed with unrelated giant history."""

    def __init__(self) -> None:
        self.history = [
            {"role": "user", "content": "z" * 100_000},
            {"role": "assistant", "content": "y" * 100_000},
        ] * 10
        self.investigation_context = None

    def set_summarize_fn(self, fn) -> None:
        pass

    def add_turn(self, _user: str, _response: str) -> None:
        pass


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


def _agent(
    provider: CapturingPlannerProvider,
    model: AssessmentModelAdapter,
    *,
    store: OversizedStore | None = None,
) -> DeterministicAgent:
    engine = NoExecutionEngine()
    return DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        conversation_store=store,
        semantic_planner=SemanticPlannerAdapter([provider]),
        semantic_relevance_verifier=PassingRelevanceVerifier(),
    )


def _model_usage(result: dict) -> dict:
    return result["execution_trace"]["runtime_metrics"]["model_usage"]


# ---------------------------------------------------------------------------
# SIMPLE: the first-pass planner call stays bounded no matter what
# unrelated history/tool/capability data exists.
# ---------------------------------------------------------------------------


def test_simple_planner_call_is_bounded_under_oversized_unrelated_data() -> None:
    provider = CapturingPlannerProvider(_direct_plan(), "Hello there!")
    model = NoModelCalls()
    agent = _agent(provider, model)

    result = agent.run_with_steps("hello")

    assert result["response"] == "Hello there!"
    assert len(provider.requests) == 1
    assert model.calls == 0
    request = provider.requests[0]
    prompt_text = request.system_prompt + request.user_prompt
    assert len(prompt_text) <= InputContextBudgetPolicy.SIMPLE.max_chars
    assert InputContextBudget.estimated_tokens(prompt_text) < 1_000
    for forbidden in ("zzzz", "yyyy"):
        assert forbidden not in prompt_text

    usage = _model_usage(result)
    assert usage["calls"] == 1
    planner_entry = usage["per_call"][0]
    assert planner_entry["purpose"] == "planner"
    assert planner_entry["input_tokens"] == 11
    assert planner_entry["estimated_input_tokens"] != 11
    assert isinstance(planner_entry["estimated_input_tokens"], int)
    assert planner_entry["estimated_input_tokens"] > 0


def test_oversized_history_and_capability_registry_do_not_enlarge_simple_call() -> None:
    plain_provider = CapturingPlannerProvider(_direct_plan(), "Hello there!")
    plain_agent = _agent(plain_provider, NoModelCalls())
    plain_result = plain_agent.run_with_steps("hello")

    oversized_provider = CapturingPlannerProvider(_direct_plan(), "Hello there!")
    oversized_agent = _agent(
        oversized_provider,
        NoModelCalls(),
        store=OversizedStore(),
    )
    # Unrelated capability catalog attached to the engine; the planner never
    # sees tools or capabilities by design.
    oversized_agent._execution_engine.capability_registry = {  # type: ignore[attr-defined]
        f"cap-{index}": "w" * 10_000 for index in range(200)
    }
    oversized_result = oversized_agent.run_with_steps("hello")

    assert plain_result["response"] == oversized_result["response"]
    plain_prompt = plain_provider.requests[0]
    oversized_prompt = oversized_provider.requests[0]
    assert oversized_prompt.system_prompt == plain_prompt.system_prompt
    assert oversized_prompt.user_prompt == plain_prompt.user_prompt
    assert len(plain_provider.requests) == len(oversized_provider.requests) == 1

    plain_usage = _model_usage(plain_result)
    oversized_usage = _model_usage(oversized_result)
    assert (
        plain_usage["per_call"][0]["estimated_input_tokens"]
        == oversized_usage["per_call"][0]["estimated_input_tokens"]
    )
    assert oversized_usage["calls"] == 1


# ---------------------------------------------------------------------------
# NORMAL: bounded direct-response context drops optional context before
# overflow and rejects mandatory overflow deterministically.
# ---------------------------------------------------------------------------


def _wide_context() -> PlannerPromptContext:
    """Valid allowlisted context close to (but under) the per-field limits."""
    return PlannerPromptContext(
        target="t" * 200,
        concept="c" * 200,
        service="s" * 200,
    )


def _near_limit_request(*, slack: int = 0) -> str:
    """Token-safety-clean request filling NORMAL up to ``slack`` spare chars.

    The complete model-visible input is the fixed Orion system instruction,
    the rendered chat system template, the user-request wrapper, and the
    request itself — exactly what the enforcement accounts for.
    """
    from src.model.protocol.orion_system_prompt import ORION_SYSTEM_PROMPT
    from src.model.protocol.prompt_loader import PromptLoader

    system = PromptLoader().render("chat_system.j2", language="en")
    wrapper = "\n\nUser: \n\nAssistant:"
    target = (
        InputContextBudgetPolicy.NORMAL.max_chars
        - len(ORION_SYSTEM_PROMPT)
        - len(system)
        - len(wrapper)
        - slack
    )
    assert target >= 5
    return ("word " * (target // 5)) + "w" * (target % 5)


def test_normal_complete_model_visible_input_hits_budget_exactly() -> None:
    from src.model.protocol.orion_system_prompt import ORION_SYSTEM_PROMPT

    model = CapturingModel()
    agent = _agent(CapturingPlannerProvider(_direct_plan(), "ignored"), model)

    request = _near_limit_request(slack=0)
    response, _validation = agent._chat_response(
        request,
        bounded_context_only=True,
        raise_errors=True,
    )

    assert response == "ok"
    prompt = model.prompts[0]
    assert request in prompt
    # Complete model-visible input, including the fixed system instruction
    # the provider sends, sits exactly at the NORMAL budget.
    complete = ORION_SYSTEM_PROMPT + prompt
    assert len(complete) == InputContextBudgetPolicy.NORMAL.max_chars
    # One more mandatory character overflows deterministically.
    with pytest.raises(InputContextBudgetError, match="exceeding"):
        agent._chat_response(
            request + "word",
            bounded_context_only=True,
            raise_errors=True,
        )


def test_normal_context_drops_optional_context_before_overflow() -> None:
    from src.model.protocol.orion_system_prompt import ORION_SYSTEM_PROMPT

    model = CapturingModel()
    agent = _agent(CapturingPlannerProvider(_direct_plan(), "ignored"), model)

    request = _near_limit_request(slack=100)
    response, _validation = agent._chat_response(
        request,
        semantic_context=_wide_context(),
        bounded_context_only=True,
        raise_errors=True,
    )

    assert response == "ok"
    assert len(model.prompts) == 1
    prompt = model.prompts[0]
    # The user request is mandatory and survives verbatim.
    assert request in prompt
    # The optional semantic context was dropped whole before overflow.
    assert "Relevant semantic context" not in prompt
    complete = ORION_SYSTEM_PROMPT + prompt
    assert len(complete) <= InputContextBudgetPolicy.NORMAL.max_chars
    # The drop happened at the boundary: only the reserved 100-char slack
    # separates the complete input from the budget.
    assert len(complete) == InputContextBudgetPolicy.NORMAL.max_chars - 100


def test_normal_context_keeps_optional_context_when_it_fits() -> None:
    model = CapturingModel()
    agent = _agent(CapturingPlannerProvider(_direct_plan(), "ignored"), model)

    agent._chat_response(
        "hello",
        semantic_context=_wide_context(),
        bounded_context_only=True,
        raise_errors=True,
    )

    assert len(model.prompts) == 1
    assert "Relevant semantic context" in model.prompts[0]
    assert len(model.prompts[0]) <= InputContextBudgetPolicy.NORMAL.max_chars


def test_normal_mandatory_overflow_fails_deterministically() -> None:
    model = CapturingModel()
    agent = _agent(CapturingPlannerProvider(_direct_plan(), "ignored"), model)

    # Long but token-safety-clean request text that alone exceeds the
    # NORMAL budget together with the mandatory system instructions.
    with pytest.raises(InputContextBudgetError, match="exceeding"):
        agent._chat_response(
            "word " * 1_250,
            bounded_context_only=True,
            raise_errors=True,
        )
    assert model.prompts == []


# ---------------------------------------------------------------------------
# Trace: the planner outcome carries the estimate and the budget class.
# ---------------------------------------------------------------------------


def test_planner_trace_records_budget_class_and_estimate() -> None:
    provider = CapturingPlannerProvider(_direct_plan(), "Hello there!")
    agent = _agent(provider, NoModelCalls())

    result = agent.run_with_steps("hello")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    planner_trace = semantic["planner"]
    assert planner_trace["input_budget_class"] == InputContextBudgetClass.SIMPLE.value
    assert planner_trace["estimated_input_tokens"] > 0
    per_call_estimate = _model_usage(result)["per_call"][0]["estimated_input_tokens"]
    assert planner_trace["estimated_input_tokens"] == per_call_estimate
