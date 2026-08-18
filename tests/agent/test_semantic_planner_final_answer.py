"""Issue #53: single-call final answers for eligible no-tool requests.

A DIRECT_ANSWER plan may carry a bounded planner-provided final answer in
the planner-output envelope.  Only the deterministic eligibility gate plus
the existing final-delivery validations may release that text: exactly one
model call (the planner) is allowed for eligible trivial requests, and
ineligible semantics must never consume the planner final text.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from src.agent.deterministic_agent import DeterministicAgent
from src.agent.semantic_loop_coordinator import (
    SemanticLoopCoordinator,
    SemanticLoopResponse,
)
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.semantic_planner_adapter import (
    ModelCallPurpose,
    PlannerProviderRequest,
    PlannerProviderResponse,
    SemanticPlannerAdapter,
    SemanticPlannerOutcome,
    SemanticPlannerOutcomeReason,
    SemanticPlannerOutcomeStatus,
    SemanticPlannerResult,
)
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.basic_calculator import CalculatorOperation, CalculatorRequest
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
from src.pipeline.semantic_plan_harness import (
    SemanticPlanHarnessResult,
    planner_final_answer_allowed,
)
from src.pipeline.semantic_plan_validation import SemanticPlanValidationResult
from src.pipeline.semantic_plan_wire import planner_output_to_wire
from src.pipeline.target_resolver import TargetResolver
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


class NoModelCalls(AssessmentModelAdapter):
    """Assessment model that must never be called on the single-call path."""

    def __init__(self) -> None:
        self.calls = 0

    def assess(self, _request: AssessmentRequest) -> str:
        self.calls += 1
        raise AssertionError("single-call path must not call the response model")

    def assess_raw(self, _prompt: str) -> str:
        self.calls += 1
        raise AssertionError("single-call path must not call the response model")


class AnswerPlannerProvider:
    def __init__(
        self,
        plan: SemanticPlan,
        final_answer: str | None = None,
    ) -> None:
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


def _gratitude_plan() -> SemanticPlan:
    return replace(_direct_plan(), concept="gratitude acknowledgement")


def _translation_plan() -> SemanticPlan:
    return replace(
        _direct_plan(),
        domain=RequestDomain.CONTENT_GENERATION,
        execution_intent=ExecutionIntent.GENERATE_CONTENT,
        concept="translation",
    )


def _knowledge_plan() -> SemanticPlan:
    return replace(_direct_plan(), concept="stable knowledge")


def _agent(
    plan: SemanticPlan,
    final_answer: str | None,
    *,
    model: AssessmentModelAdapter | None = None,
) -> tuple[DeterministicAgent, NoExecutionEngine, AssessmentModelAdapter]:
    engine = NoExecutionEngine()
    model = model or NoModelCalls()
    planner = SemanticPlannerAdapter([AnswerPlannerProvider(plan, final_answer)])
    return (
        DeterministicAgent(
            engine,  # type: ignore[arg-type]
            model,
            semantic_planner=planner,
        ),
        engine,
        model,
    )


def _semantic_loop(result: dict) -> dict:
    return result["execution_trace"]["runtime_metrics"]["semantic_loop"]


def _model_usage(result: dict) -> dict:
    return result["execution_trace"]["runtime_metrics"]["model_usage"]


# ---------------------------------------------------------------------------
# Eligibility gate unit tests
# ---------------------------------------------------------------------------


def test_eligibility_gate_accepts_only_trivial_direct_answers() -> None:
    assert planner_final_answer_allowed(_direct_plan())
    assert planner_final_answer_allowed(
        replace(_direct_plan(), freshness=FreshnessRequirement.HISTORICAL)
    )
    assert planner_final_answer_allowed(_translation_plan())

    assert not planner_final_answer_allowed(
        replace(_direct_plan(), route=SemanticPlanRoute.CAPABILITY_ASSISTED)
    )
    for freshness in (
        FreshnessRequirement.CURRENT,
        FreshnessRequirement.LATEST,
        FreshnessRequirement.RECENT,
        FreshnessRequirement.REAL_TIME,
        FreshnessRequirement.UNSPECIFIED,
        FreshnessRequirement.UNKNOWN,
    ):
        assert not planner_final_answer_allowed(
            replace(_direct_plan(), freshness=freshness)
        )
    for domain in (
        RequestDomain.EXTERNAL_INFORMATION,
        RequestDomain.ENVIRONMENT,
        RequestDomain.ACTION,
    ):
        assert not planner_final_answer_allowed(replace(_direct_plan(), domain=domain))
    for intent in (
        ExecutionIntent.INSPECT_READ_ONLY,
        ExecutionIntent.MUTATE_ENVIRONMENT,
    ):
        assert not planner_final_answer_allowed(
            replace(_direct_plan(), execution_intent=intent)
        )
    assert not planner_final_answer_allowed(
        replace(
            _direct_plan(),
            deterministic_compute=DeterministicComputeIntent.REQUIRED,
        )
    )
    assert not planner_final_answer_allowed(
        replace(
            _direct_plan(),
            calculation=CalculatorRequest(
                CalculatorOperation.AVERAGE,
                values=(Decimal("20"), Decimal("40"), Decimal("60")),
            ),
        )
    )
    assert not planner_final_answer_allowed(
        replace(_direct_plan(), clarification=ClarificationState.REQUIRED)
    )
    assert not planner_final_answer_allowed(
        replace(
            _direct_plan(),
            target=TargetReference(TargetReferenceKind.EXPLICIT, "localhost"),
        )
    )
    assert not planner_final_answer_allowed(
        replace(_direct_plan(), explicit_url="https://example.com/status")
    )
    for sources in (
        (SourceConstraint.INTERNET,),
        (SourceConstraint.LINUX,),
        (SourceConstraint.URL_ONLY,),
    ):
        assert not planner_final_answer_allowed(
            replace(_direct_plan(), source_constraints=sources)
        )


# ---------------------------------------------------------------------------
# Single-call delivery behavior (agent level)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user_text", "plan", "answer"),
    (
        ("hello", _direct_plan(), "Hello! How can I help you?"),
        ("Cảm ơn bạn nhé", _gratitude_plan(), "Không có gì!"),
        ("Translate 'xin chào' to English.", _translation_plan(), "Hello."),
        (
            "What is the capital of France?",
            _knowledge_plan(),
            "The capital of France is Paris.",
        ),
    ),
)
def test_eligible_trivial_requests_are_answered_in_one_planner_call(
    user_text: str,
    plan: SemanticPlan,
    answer: str,
) -> None:
    model = NoModelCalls()
    agent, engine, _model = _agent(plan, answer, model=model)

    result = agent.run_with_steps(user_text)

    semantic = _semantic_loop(result)
    assert result["response"] == answer
    assert semantic["terminal_state"] == "DONE"
    assert semantic["failure"] is None
    assert semantic["state_history"] == [
        "PLAN",
        "VALIDATE",
        "ASSESS/RESPOND",
        "DONE",
    ]
    reasons = [record["reason"] for record in semantic["states"]]
    assert "planner_answer" in reasons
    assert "direct_answer" not in reasons
    assert semantic["postconditions"] == {"passed": True, "violations": []}
    assert result["steps"] == []
    assert result["investigation"] is None
    assert engine.execute_calls == 0
    assert model.calls == 0


def test_trivial_direct_answer_records_exactly_one_model_call() -> None:
    model = NoModelCalls()
    agent, engine, _model = _agent(_direct_plan(), "Hello there!", model=model)

    result = agent.run_with_steps("hello")

    semantic = _semantic_loop(result)
    assert result["response"] == "Hello there!"
    assert semantic["postconditions"]["passed"] is True

    usage = _model_usage(result)
    assert usage["calls"] == 1
    assert usage["dropped_calls"] == 0
    assert set(usage["by_purpose"]) == {"planner"}
    planner_usage = usage["by_purpose"]["planner"]
    assert planner_usage["calls"] == 1
    assert planner_usage["input_tokens"] == 11
    assert planner_usage["reasoning_tokens"] == 3
    assert planner_usage["visible_output_tokens"] == 9
    assert planner_usage["total_output_tokens"] == 12
    assert [entry["purpose"] for entry in usage["per_call"]] == ["planner"]
    assert model.calls == 0
    assert engine.execute_calls == 0
    json.dumps(usage)


# ---------------------------------------------------------------------------
# Ineligible semantics must never consume planner final text
# ---------------------------------------------------------------------------


def test_current_freshness_plan_never_uses_planner_final_text() -> None:
    plan = replace(_direct_plan(), freshness=FreshnessRequirement.CURRENT)
    model = NoModelCalls()
    agent, engine, _model = _agent(plan, "Fake current answer.", model=model)

    result = agent.run_with_steps("Who is the current holder of this office?")

    semantic = _semantic_loop(result)
    assert "Fake current answer" not in result["response"]
    assert semantic["terminal_state"] == "FAIL"
    assert semantic["failure"] == "validation_failed"
    assert engine.execute_calls == 0
    assert model.calls == 0


def test_compute_plan_never_uses_planner_final_text() -> None:
    plan = replace(
        _direct_plan(),
        deterministic_compute=DeterministicComputeIntent.REQUIRED,
        calculation=CalculatorRequest(
            CalculatorOperation.AVERAGE,
            values=(Decimal("20"), Decimal("40"), Decimal("60")),
        ),
    )
    model = NoModelCalls()
    agent, engine, _model = _agent(plan, "Wrong result: 100", model=model)

    result = agent.run_with_steps("average 20 40 60")

    semantic = _semantic_loop(result)
    assert result["response"] == "Result: 40."
    assert "Wrong result" not in result["response"]
    assert semantic["terminal_state"] == "DONE"
    assert semantic["calculator_calls"] == 1
    assert engine.execute_calls == 0
    assert model.calls == 0


def test_mutation_request_never_uses_planner_final_text() -> None:
    model = NoModelCalls()
    agent, engine, _model = _agent(_direct_plan(), "Restarted for you!", model=model)

    result = agent.run_with_steps("restart nginx")

    assert "Restarted for you" not in result["response"]
    assert engine.execute_calls == 0
    assert model.calls == 0


def test_guard_blocks_unsafe_planner_final_text() -> None:
    model = NoModelCalls()
    agent, engine, _model = _agent(
        _gratitude_plan(),
        "Orion has restarted nginx and deleted the temporary files.",
        model=model,
    )

    result = agent.run_with_steps("Cảm ơn bạn nhé")

    semantic = _semantic_loop(result)
    assert "restarted nginx" not in result["response"]
    assert "Orion chỉ đọc" in result["response"]
    assert semantic["terminal_state"] == "DONE"
    assert semantic["postconditions"]["passed"] is False
    assert "read_only_boundary" in semantic["postconditions"]["violations"]
    assert engine.execute_calls == 0
    assert model.calls == 0


# ---------------------------------------------------------------------------
# Coordinator-level single-call routing
# ---------------------------------------------------------------------------


class _StaticPlanner:
    def __init__(self, outcome: SemanticPlannerOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    def plan_safely(self, raw_request, *, context=None, request_id=None):
        self.calls += 1
        return self.outcome


class _StaticValidator:
    def __init__(self, result: SemanticPlanHarnessResult) -> None:
        self.result = result
        self.calls = 0

    def validate(self, plan, *, raw_request):
        self.calls += 1
        return self.result


class _StaticBinder:
    def bind(self, harness, *, raw_request, timeframe=None):
        raise AssertionError("direct-answer plan must not bind")


def _harness(plan: SemanticPlan) -> SemanticPlanHarnessResult:
    return SemanticPlanHarnessResult(
        validation=SemanticPlanValidationResult.valid(plan)
    )


def _outcome_with_answer(
    plan: SemanticPlan,
    answer: str,
) -> SemanticPlannerOutcome:
    return SemanticPlannerOutcome(
        status=SemanticPlannerOutcomeStatus.VALID,
        reason=SemanticPlannerOutcomeReason.PLAN_VALID,
        plan=plan,
        result=SemanticPlannerResult(
            plan=plan,
            provider="test",
            model="semantic-test",
            raw_usage=None,
            purpose=ModelCallPurpose.PLANNER,
            latency_ms=1.0,
            final_answer=answer,
        ),
    )


def _response(text: str = "done") -> SemanticLoopResponse:
    return SemanticLoopResponse(
        text=text,
        answer_strategy="DETERMINISTIC_TEMPLATE",
        model_used=False,
    )


def _fail_execute(_frame):
    raise AssertionError("no-tool plan must not execute")


def _coordinator(
    plan: SemanticPlan,
    answer: str,
    *,
    direct,
    accept,
) -> SemanticLoopCoordinator:
    return SemanticLoopCoordinator(
        planner=_StaticPlanner(_outcome_with_answer(plan, answer)),
        validator=_StaticValidator(_harness(plan)),
        binder_factory=lambda: _StaticBinder(),
        execute=_fail_execute,
        respond_direct=direct,
        respond_assessment=lambda _request, _investigation: _response(),
        respond_failure=lambda _request, _failure, _detail: _response("failed"),
        accept_planner_answer=accept,
    )


def test_eligible_planner_answer_skips_response_model_call() -> None:
    plan = _direct_plan()
    direct_calls = 0
    answer_calls: list[tuple[str, str]] = []

    def direct(_request, _context):
        nonlocal direct_calls
        direct_calls += 1
        return _response("direct")

    def accept(request: str, answer: str):
        answer_calls.append((request, answer))
        return _response("planner-answer")

    result = _coordinator(plan, "Xin chào!", direct=direct, accept=accept).run("hello")

    assert result.succeeded
    assert result.response.text == "planner-answer"
    assert answer_calls == [("hello", "Xin chào!")]
    assert direct_calls == 0
    reasons = [record.reason for record in result.records]
    assert "planner_answer" in reasons
    assert "direct_answer" not in reasons


def test_eligible_planner_answer_without_callback_uses_direct_response() -> None:
    plan = _direct_plan()
    direct_calls = 0

    def direct(_request, _context):
        nonlocal direct_calls
        direct_calls += 1
        return _response("direct")

    result = SemanticLoopCoordinator(
        planner=_StaticPlanner(_outcome_with_answer(plan, "Xin chào!")),
        validator=_StaticValidator(_harness(plan)),
        binder_factory=lambda: _StaticBinder(),
        execute=_fail_execute,
        respond_direct=direct,
        respond_assessment=lambda _request, _investigation: _response(),
        respond_failure=lambda _request, _failure, _detail: _response("failed"),
    ).run("hello")

    assert result.succeeded
    assert result.response.text == "direct"
    assert direct_calls == 1
    assert "planner_answer" not in [record.reason for record in result.records]


def test_ineligible_plan_ignores_planner_final_text() -> None:
    plan = replace(_direct_plan(), freshness=FreshnessRequirement.CURRENT)
    direct_calls = 0
    answer_calls = 0

    def direct(_request, _context):
        nonlocal direct_calls
        direct_calls += 1
        return _response("direct")

    def accept(_request: str, _answer: str):
        nonlocal answer_calls
        answer_calls += 1
        return _response("planner-answer")

    result = _coordinator(
        plan, "Fake current answer.", direct=direct, accept=accept
    ).run("hello")

    assert result.succeeded
    assert result.response.text == "direct"
    assert direct_calls == 1
    assert answer_calls == 0
    reasons = [record.reason for record in result.records]
    assert "planner_answer" not in reasons
    assert "direct_answer" in reasons


def test_compute_plan_never_uses_planner_final_text_at_coordinator_level() -> None:
    plan = replace(
        _direct_plan(),
        deterministic_compute=DeterministicComputeIntent.REQUIRED,
        calculation=CalculatorRequest(
            CalculatorOperation.AVERAGE,
            values=(Decimal("20"), Decimal("40"), Decimal("60")),
        ),
    )
    answer_calls = 0

    def accept(_request: str, _answer: str):
        nonlocal answer_calls
        answer_calls += 1
        return _response("planner-answer")

    coordinator = SemanticLoopCoordinator(
        planner=_StaticPlanner(_outcome_with_answer(plan, "Wrong result: 100")),
        validator=_StaticValidator(_harness(plan)),
        binder_factory=lambda: _StaticBinder(),
        execute=_fail_execute,
        respond_direct=lambda _request, _context: _response(),
        respond_assessment=lambda _request, _investigation: _response(),
        respond_compute=lambda _request, _plan, result: _response(
            f"Result: {result.value}"
        ),
        respond_failure=lambda _request, _failure, _detail: _response("failed"),
        accept_planner_answer=accept,
    )

    result = coordinator.run("average 20 40 60")

    assert result.succeeded
    assert result.response.text == "Result: 40"
    assert answer_calls == 0
    assert result.calculator_calls == 1
