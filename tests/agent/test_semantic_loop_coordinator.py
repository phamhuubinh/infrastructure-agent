from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType

import pytest

from src.agent.conversation_store import ConversationStore
from src.agent.deterministic_agent import DeterministicAgent
from src.agent.semantic_loop_coordinator import (
    SemanticLoopConfig,
    SemanticLoopCoordinator,
    SemanticLoopFailure,
    SemanticLoopResponse,
    SemanticLoopState,
)
from src.agent.session_investigation_context import SessionInvestigationContext
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.semantic_planner_adapter import (
    SemanticPlannerOutcome,
    SemanticPlannerOutcomeReason,
    SemanticPlannerOutcomeStatus,
)
from src.model.semantic_relevance_verifier import (
    SemanticRelevanceDecision,
    SemanticRelevanceReason,
    SemanticRelevanceResult,
)
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.basic_calculator import (
    CalculatorOperation,
    CalculatorRequest,
)
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.execution_budget import ExecutionBudget, ExecutionBudgetConfig
from src.pipeline.execution_runtime import RuntimeMetrics
from src.pipeline.external_verification import (
    ExternalDocument,
    ExternalEvidenceRelevance,
    ExternalVerificationOutcome,
)
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.request_frame import RequestFrame
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
from src.pipeline.semantic_plan_binding import (
    BoundSemanticCapability,
    SemanticPlanBindingResult,
)
from src.pipeline.semantic_plan_harness import SemanticPlanHarnessResult
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
)
from src.pipeline.target_resolver import TargetResolver
from src.tool.internet_tool import InternetTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


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


def _compute_plan() -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        concept="average",
        deterministic_compute=DeterministicComputeIntent.REQUIRED,
        calculation=CalculatorRequest(
            CalculatorOperation.AVERAGE,
            values=(Decimal("20"), Decimal("40"), Decimal("60")),
        ),
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _external_plan(*, url: str | None = None) -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.EXTERNAL_INFORMATION,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        source_constraints=(
            (SourceConstraint.URL_ONLY,) if url else (SourceConstraint.INTERNET,)
        ),
        freshness=FreshnessRequirement.CURRENT,
        concept="current version",
        explicit_url=url,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _content_literal_plan() -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.CONTENT_GENERATION,
        execution_intent=ExecutionIntent.GENERATE_CONTENT,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        concept="configuration example",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


@dataclass
class StaticPlanner:
    outcome: SemanticPlannerOutcome
    calls: int = 0

    def plan_safely(self, raw_request, *, context=None, request_id=None):
        self.calls += 1
        return self.outcome


@dataclass
class StaticValidator:
    result: SemanticPlanHarnessResult
    calls: int = 0

    def validate(self, plan, *, raw_request):
        self.calls += 1
        return self.result


@dataclass
class StaticBinder:
    result: SemanticPlanBindingResult
    calls: int = 0

    def bind(self, harness, *, raw_request, timeframe=None):
        self.calls += 1
        return self.result


def _outcome(plan: SemanticPlan) -> SemanticPlannerOutcome:
    return SemanticPlannerOutcome(
        status=SemanticPlannerOutcomeStatus.VALID,
        reason=SemanticPlannerOutcomeReason.PLAN_VALID,
        plan=plan,
    )


def _harness(
    plan: SemanticPlan,
    *,
    valid: bool = True,
) -> SemanticPlanHarnessResult:
    validation = (
        SemanticPlanValidationResult.valid(plan)
        if valid
        else SemanticPlanValidationResult.reject(
            SemanticPlanValidationReason.MUTATION_UNSAFE,
            plan=plan,
        )
    )
    return SemanticPlanHarnessResult(validation=validation)


def _binding(plan: SemanticPlan, capability_count: int) -> SemanticPlanBindingResult:
    frame = RequestFrame(
        raw_request="check cpu",
        concepts=("cpu",),
        target_raw="localhost",
        target_resolved="localhost",
        request_domain=RequestDomain.ENVIRONMENT,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
    )
    request = InvestigationRequest(
        raw_request=frame.raw_request,
        target="localhost",
        request_frame=frame,
    )
    capabilities = tuple(
        BoundSemanticCapability(
            reference=CapabilityReference(
                name=f"Capability {index}",
                evidence_name=f"Evidence {index}",
                required=True,
                estimated_cost=0.1,
            ),
            source="localhost",
            resource=f"resource_{index}",
            arguments=MappingProxyType(
                {"source": "localhost", "resource": f"resource_{index}"}
            ),
        )
        for index in range(capability_count)
    )
    return SemanticPlanBindingResult(
        validation=SemanticPlanValidationResult.valid(plan),
        request=request,
        capabilities=capabilities,
        freshness=plan.freshness,
    )


def _investigation(
    frame: RequestFrame,
    *,
    tool_calls: int,
    rounds: int = 1,
    budget_config: ExecutionBudgetConfig | None = None,
) -> InvestigationRequest:
    config = budget_config or ExecutionBudgetConfig()
    budget = ExecutionBudget(config)
    for _ in range(rounds):
        assert budget.start_round(0, 0.0)
    return InvestigationRequest(
        raw_request=frame.raw_request,
        target=frame.target_resolved,
        request_frame=frame,
        runtime_metrics=RuntimeMetrics(tool_calls=tool_calls),
        execution_budget=budget,
    )


def _response(text: str = "done") -> SemanticLoopResponse:
    return SemanticLoopResponse(
        text=text,
        answer_strategy="DETERMINISTIC_TEMPLATE",
        model_used=False,
    )


def _coordinator(
    *,
    planner: StaticPlanner,
    validator: StaticValidator,
    binder: StaticBinder,
    execute,
    direct,
    assess,
    failure,
    config: SemanticLoopConfig | None = None,
) -> SemanticLoopCoordinator:
    return SemanticLoopCoordinator(
        planner=planner,
        validator=validator,
        binder_factory=lambda: binder,
        execute=execute,
        respond_direct=direct,
        respond_assessment=assess,
        respond_failure=failure,
        config=config,
    )


def test_no_tool_request_stops_without_binding_or_execution() -> None:
    plan = _direct_plan()
    binder = StaticBinder(_binding(_capability_plan(), 1))
    execute_calls = 0

    def execute(_frame):
        nonlocal execute_calls
        execute_calls += 1
        raise AssertionError("no-tool plan must not execute")

    coordinator = _coordinator(
        planner=StaticPlanner(_outcome(plan)),
        validator=StaticValidator(_harness(plan)),
        binder=binder,
        execute=execute,
        direct=lambda _request, _context: _response("hello"),
        assess=lambda _request, _investigation: _response(),
        failure=lambda _request, _failure, _detail: _response("failed"),
    )

    result = coordinator.run("hello")

    assert result.succeeded
    assert [record.state for record in result.records] == [
        SemanticLoopState.PLAN,
        SemanticLoopState.VALIDATE,
        SemanticLoopState.ASSESS_RESPOND,
        SemanticLoopState.DONE,
    ]
    assert binder.calls == 0
    assert execute_calls == 0
    assert result.execution_cycles == 0
    assert result.to_trace_dict()["final_response_count"] == 1


def test_one_tool_request_completes_in_one_bounded_cycle() -> None:
    plan = _capability_plan()
    binding = _binding(plan, 1)
    execute_calls = 0
    assessment_calls = 0

    def execute(frame: RequestFrame) -> InvestigationRequest:
        nonlocal execute_calls
        execute_calls += 1
        return _investigation(frame, tool_calls=1)

    def assess(_request, _investigation):
        nonlocal assessment_calls
        assessment_calls += 1
        return _response("assessed")

    coordinator = _coordinator(
        planner=StaticPlanner(_outcome(plan)),
        validator=StaticValidator(_harness(plan)),
        binder=StaticBinder(binding),
        execute=execute,
        direct=lambda _request, _context: _response(),
        assess=assess,
        failure=lambda _request, _failure, _detail: _response("failed"),
    )

    result = coordinator.run("check cpu")

    assert result.succeeded
    assert execute_calls == 1
    assert assessment_calls == 1
    assert result.execution_cycles == 1
    assert result.planned_tool_calls == 1
    assert result.actual_tool_calls == 1
    assert result.budget is not None
    assert result.budget.rounds == 1


def test_structured_compute_uses_calculator_without_tool_execution() -> None:
    plan = _compute_plan()
    execute_calls = 0

    def execute(_frame):
        nonlocal execute_calls
        execute_calls += 1
        raise AssertionError("calculator plan must not dispatch a tool")

    coordinator = SemanticLoopCoordinator(
        planner=StaticPlanner(_outcome(plan)),
        validator=StaticValidator(_harness(plan)),
        binder_factory=lambda: StaticBinder(_binding(_capability_plan(), 1)),
        execute=execute,
        respond_direct=lambda _request, _context: _response(),
        respond_assessment=lambda _request, _investigation: _response(),
        respond_compute=lambda _request, _plan, result: _response(
            f"Result: {result.value}"
        ),
        respond_failure=lambda _request, _failure, _detail: _response("failed"),
    )

    result = coordinator.run("average 20 40 60")

    assert result.succeeded
    assert result.response.text == "Result: 40"
    assert result.calculator_calls == 1
    assert result.actual_tool_calls == 0
    assert execute_calls == 0
    assert result.to_trace_dict()["calculator_calls"] == 1
    assert result.to_trace_dict()["calculator"]["operation"] == "average"


def test_multi_step_evidence_request_remains_one_finite_execution_cycle() -> None:
    plan = _capability_plan()
    config = SemanticLoopConfig(
        execution_budget=ExecutionBudgetConfig(
            max_rounds=2,
            max_capabilities=4,
            max_total_duration=10,
            max_estimated_cost=4,
        )
    )
    execute_calls = 0

    def execute(frame: RequestFrame) -> InvestigationRequest:
        nonlocal execute_calls
        execute_calls += 1
        return _investigation(
            frame,
            tool_calls=3,
            rounds=2,
            budget_config=config.execution_budget,
        )

    coordinator = _coordinator(
        planner=StaticPlanner(_outcome(plan)),
        validator=StaticValidator(_harness(plan)),
        binder=StaticBinder(_binding(plan, 3)),
        execute=execute,
        direct=lambda _request, _context: _response(),
        assess=lambda _request, _investigation: _response("bounded evidence"),
        failure=lambda _request, _failure, _detail: _response("failed"),
        config=config,
    )

    result = coordinator.run("check cpu memory and disk")

    assert result.succeeded
    assert execute_calls == 1
    assert result.execution_cycles == 1
    assert result.planned_tool_calls == 3
    assert result.actual_tool_calls == 3
    assert len(result.records) == 5


def test_invalid_plan_and_pre_execution_budget_failure_never_execute() -> None:
    plan = _capability_plan()
    execute_calls = 0

    def execute(_frame):
        nonlocal execute_calls
        execute_calls += 1
        raise AssertionError("invalid or over-budget plan must not execute")

    invalid = _coordinator(
        planner=StaticPlanner(_outcome(plan)),
        validator=StaticValidator(_harness(plan, valid=False)),
        binder=StaticBinder(_binding(plan, 1)),
        execute=execute,
        direct=lambda _request, _context: _response(),
        assess=lambda _request, _investigation: _response(),
        failure=lambda _request, _failure, _detail: _response("invalid"),
    ).run("restart nginx")
    over_budget = _coordinator(
        planner=StaticPlanner(_outcome(plan)),
        validator=StaticValidator(_harness(plan)),
        binder=StaticBinder(_binding(plan, 2)),
        execute=execute,
        direct=lambda _request, _context: _response(),
        assess=lambda _request, _investigation: _response(),
        failure=lambda _request, _failure, _detail: _response("over budget"),
        config=SemanticLoopConfig(
            execution_budget=ExecutionBudgetConfig(max_capabilities=1)
        ),
    ).run("check cpu")

    assert invalid.failure is SemanticLoopFailure.VALIDATION_FAILED
    assert over_budget.failure is SemanticLoopFailure.BUDGET_EXHAUSTED
    assert execute_calls == 0


def test_provider_execution_and_state_limit_failures_terminate_once() -> None:
    plan = _capability_plan()
    provider_failure = SemanticPlannerOutcome(
        status=SemanticPlannerOutcomeStatus.FAILED,
        reason=SemanticPlannerOutcomeReason.PROVIDER_ERROR,
    )
    failure_responses = 0

    def failure(_request, _failure, _detail):
        nonlocal failure_responses
        failure_responses += 1
        return _response("safe failure")

    provider_result = _coordinator(
        planner=StaticPlanner(provider_failure),
        validator=StaticValidator(_harness(plan)),
        binder=StaticBinder(_binding(plan, 1)),
        execute=lambda _frame: _investigation(_frame, tool_calls=1),
        direct=lambda _request, _context: _response(),
        assess=lambda _request, _investigation: _response(),
        failure=failure,
    ).run("check cpu")
    execution_result = _coordinator(
        planner=StaticPlanner(_outcome(plan)),
        validator=StaticValidator(_harness(plan)),
        binder=StaticBinder(_binding(plan, 1)),
        execute=lambda _frame: (_ for _ in ()).throw(
            RuntimeError("SECRET_CHAIN_OF_THOUGHT")
        ),
        direct=lambda _request, _context: _response(),
        assess=lambda _request, _investigation: _response(),
        failure=failure,
    ).run("check cpu")
    response_result = _coordinator(
        planner=StaticPlanner(_outcome(_direct_plan())),
        validator=StaticValidator(_harness(_direct_plan())),
        binder=StaticBinder(_binding(plan, 1)),
        execute=lambda _frame: _investigation(_frame, tool_calls=1),
        direct=lambda _request, _context: (_ for _ in ()).throw(
            ConnectionError("SECRET_PROVIDER_DETAIL")
        ),
        assess=lambda _request, _investigation: _response(),
        failure=failure,
    ).run("hello")
    state_limit_result = _coordinator(
        planner=StaticPlanner(_outcome(_direct_plan())),
        validator=StaticValidator(_harness(_direct_plan())),
        binder=StaticBinder(_binding(plan, 1)),
        execute=lambda _frame: _investigation(_frame, tool_calls=1),
        direct=lambda _request, _context: _response(),
        assess=lambda _request, _investigation: _response(),
        failure=failure,
        config=SemanticLoopConfig(max_state_transitions=2),
    ).run("hello")

    assert provider_result.failure is SemanticLoopFailure.PROVIDER_FAILURE
    assert execution_result.failure is SemanticLoopFailure.EXECUTION_FAILED
    assert response_result.failure is SemanticLoopFailure.RESPONSE_FAILED
    assert state_limit_result.failure is SemanticLoopFailure.STATE_LIMIT
    assert failure_responses == 4
    assert "SECRET_CHAIN_OF_THOUGHT" not in json.dumps(execution_result.to_trace_dict())
    assert execution_result.failure_detail == "RuntimeError"
    assert "SECRET_PROVIDER_DETAIL" not in json.dumps(response_result.to_trace_dict())


class LoopAssessmentModel(AssessmentModelAdapter):
    def __init__(self) -> None:
        self.assess_calls = 0
        self.requests: list[AssessmentRequest] = []
        self.raw_prompts: list[str] = []

    def assess(self, assessment_request: AssessmentRequest) -> str:
        self.assess_calls += 1
        self.requests.append(assessment_request)
        return "Bounded assessment."

    def assess_raw(self, _prompt: str) -> str:
        self.raw_prompts.append(_prompt)
        if "compact final-answer relevance verifier" in _prompt:
            return '{"decision":"aligned","reason":"aligned"}'
        return "Hello."


@dataclass
class CountingRelevanceVerifier:
    calls: int = 0

    def verify(self, _request, _plan, _draft) -> SemanticRelevanceResult:
        self.calls += 1
        return SemanticRelevanceResult(
            SemanticRelevanceDecision.ALIGNED,
            SemanticRelevanceReason.ALIGNED,
        )


class AgentLoopExecutionEngine:
    def __init__(self) -> None:
        registry = TargetRegistry()
        registry.add("localhost")
        self.knowledge_tool = KnowledgeTool(registry)
        self.target_resolver = TargetResolver(registry)
        self.execution_budget_config = ExecutionBudgetConfig()
        self.execute_calls = 0

    def execute(self, frame: RequestFrame) -> InvestigationRequest:
        self.execute_calls += 1
        return _investigation(frame, tool_calls=1)


class ExternalLoopExecutionEngine(AgentLoopExecutionEngine):
    def __init__(self) -> None:
        registry = TargetRegistry()
        registry.add("localhost")
        registry.register_tool("internet", InternetTool())
        self.knowledge_tool = KnowledgeTool(registry)
        self.target_resolver = TargetResolver(registry)
        self.execution_budget_config = ExecutionBudgetConfig()
        self.execute_calls = 0


@dataclass
class FakeExternalVerifier:
    outcome: ExternalVerificationOutcome
    frames: list[RequestFrame]

    def collect(
        self, frame: RequestFrame, _user_request: str
    ) -> ExternalVerificationOutcome:
        self.frames.append(frame)
        return self.outcome


def test_deterministic_agent_uses_coordinator_for_capability_plan() -> None:
    plan = _capability_plan()
    planner = StaticPlanner(_outcome(plan))
    engine = AgentLoopExecutionEngine()
    model = LoopAssessmentModel()
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=planner,  # type: ignore[arg-type]
    )

    result = agent.run_with_steps("check cpu on localhost")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    stages = result["execution_trace"]["stages"]
    assert result["response"]
    assert engine.execute_calls == 1
    assert planner.calls == 1
    assert model.assess_calls == 1
    assert semantic["terminal_state"] == "DONE"
    assert semantic["state_history"] == [
        "PLAN",
        "VALIDATE",
        "EXECUTE",
        "ASSESS/RESPOND",
        "DONE",
    ]
    assert semantic["execution_cycles"] == 1
    assert semantic["actual_tool_calls"] == 1
    assert semantic["final_response_count"] == 1
    assert stages["semantic_plan"]["status"] == "SUCCEEDED"
    assert stages["semantic_validate"]["status"] == "SUCCEEDED"
    assert stages["semantic_execute"]["status"] == "SUCCEEDED"
    assert stages["semantic_assess_respond"]["status"] == "SUCCEEDED"
    assert stages["semantic_done"]["status"] == "SUCCEEDED"
    assert stages["semantic_fail"]["status"] == "SKIPPED"


def test_deterministic_agent_returns_exact_structured_calculator_result() -> None:
    planner = StaticPlanner(_outcome(_compute_plan()))
    engine = AgentLoopExecutionEngine()
    model = LoopAssessmentModel()
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=planner,  # type: ignore[arg-type]
    )

    result = agent.run_with_steps("Average 20, 40, and 60")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert result["response"] == "Result: 40."
    assert semantic["calculator_calls"] == 1
    assert semantic["actual_tool_calls"] == 0
    assert engine.execute_calls == 0
    assert model.assess_calls == 0
    assert model.raw_prompts == []


def test_relevance_verifier_runs_only_after_hard_postconditions_need_it() -> None:
    plan = _direct_plan()
    verifier = CountingRelevanceVerifier()
    agent = DeterministicAgent(
        AgentLoopExecutionEngine(),  # type: ignore[arg-type]
        LoopAssessmentModel(),
        semantic_planner=StaticPlanner(_outcome(plan)),  # type: ignore[arg-type]
        semantic_relevance_verifier=verifier,
    )
    model_draft = SemanticLoopResponse(
        text="Hello.",
        answer_strategy="CHAT",
        model_used=True,
    )
    deterministic_draft = SemanticLoopResponse(
        text="Hello.",
        answer_strategy="DETERMINISTIC_TEMPLATE",
        model_used=False,
    )

    aligned = agent._semantic_loop_verify_response(  # noqa: SLF001
        "Say hello",
        model_draft,
        plan,
        _harness(plan),
        None,
        None,
    )
    agent._semantic_loop_verify_response(  # noqa: SLF001
        "Say hello",
        deterministic_draft,
        plan,
        _harness(plan),
        None,
        None,
    )
    current_plan = replace(plan, freshness=FreshnessRequirement.CURRENT)
    hard_rejection = agent._semantic_loop_verify_response(  # noqa: SLF001
        "What is the current value?",
        SemanticLoopResponse(
            text="The current value is 100.",
            answer_strategy="CHAT",
            model_used=True,
        ),
        current_plan,
        _harness(current_plan),
        None,
        None,
    )

    assert verifier.calls == 1
    assert aligned.postcondition_validation["relevance"]["decision"] == "aligned"
    assert "semantic_not_aligned" not in aligned.postcondition_validation["violations"]
    assert hard_rejection.postcondition_validation["violations"] == [
        "current_unverified"
    ]


def test_ambiguous_structured_compute_is_rejected_before_execution() -> None:
    plan = _compute_plan()
    invalid = SemanticPlan(
        route=plan.route,
        domain=plan.domain,
        execution_intent=plan.execution_intent,
        source_constraints=plan.source_constraints,
        freshness=plan.freshness,
        concept=plan.concept,
        deterministic_compute=plan.deterministic_compute,
        calculation=CalculatorRequest(CalculatorOperation.AVERAGE),
        clarification=plan.clarification,
    )
    engine = AgentLoopExecutionEngine()
    model = LoopAssessmentModel()
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=StaticPlanner(_outcome(invalid)),  # type: ignore[arg-type]
    )

    result = agent.run_with_steps("Compute the average")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert semantic["failure"] == "validation_failed"
    assert semantic["failure_detail"] == "compute_invalid"
    assert engine.execute_calls == 0
    assert model.assess_calls == 0


def test_semantic_current_info_uses_verified_external_executor_path() -> None:
    document = ExternalDocument(
        title="OpenSSH release",
        url="https://example.com/openssh",
        content="OpenSSH current release information",
        provider="fake",
        retrieved_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        relevance=ExternalEvidenceRelevance.SUFFICIENT,
    )
    unrelated = ExternalDocument(
        title="Unrelated page",
        url="https://unrelated.example/page",
        content="unrelated content",
        provider="fake",
        retrieved_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        relevance=ExternalEvidenceRelevance.IRRELEVANT,
    )
    outcome = ExternalVerificationOutcome(
        evidence=EvidencePackage(
            "Internet verification",
            "Current External Information",
            data={"passage": "OpenSSH current release information"},
            source="internet",
        ),
        documents=(document, unrelated),
        search_calls=1,
        fetch_calls=1,
    )
    verifier = FakeExternalVerifier(outcome, [])
    engine = ExternalLoopExecutionEngine()
    model = LoopAssessmentModel()
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        external_verifier=verifier,  # type: ignore[arg-type]
        semantic_planner=StaticPlanner(_outcome(_external_plan())),  # type: ignore[arg-type]
    )

    result = agent.run_with_steps("What is the current OpenSSH release?")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert verifier.frames
    assert engine.execute_calls == 0
    assert model.assess_calls == 1
    assert semantic["actual_tool_calls"] == 2
    assert "https://example.com/openssh" in result["response"]
    assert "unrelated.example" not in result["response"]
    model_documents = model.requests[0].evidence[0].data["documents"]
    assert [item["url"] for item in model_documents] == ["https://example.com/openssh"]


@pytest.mark.parametrize(
    "user_request",
    (
        "What is the latest OpenSSH version?",
        "What is in the news today?",
        "What is the current Python version?",
        "Who is the current CEO?",
        "What is the current price?",
        "What is the current weather?",
    ),
)
def test_semantic_external_unavailable_never_uses_model_memory(
    user_request: str,
) -> None:
    verifier = FakeExternalVerifier(
        ExternalVerificationOutcome(failures=("search unavailable",)),
        [],
    )
    engine = ExternalLoopExecutionEngine()
    model = LoopAssessmentModel()
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        external_verifier=verifier,  # type: ignore[arg-type]
        semantic_planner=StaticPlanner(_outcome(_external_plan())),  # type: ignore[arg-type]
    )

    result = agent.run_with_steps(user_request)

    assert "cannot be verified" in result["response"]
    assert len(verifier.frames) == 1
    assert model.assess_calls == 0
    assert engine.execute_calls == 0
    assert (
        result["execution_trace"]["stages"]["final_response_postconditions"]["status"]
        == "SUCCEEDED"
    )


def test_semantic_explicit_url_uses_external_fetch_path() -> None:
    verifier = FakeExternalVerifier(
        ExternalVerificationOutcome(failures=("fetch unavailable",)),
        [],
    )
    engine = ExternalLoopExecutionEngine()
    model = LoopAssessmentModel()
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        external_verifier=verifier,  # type: ignore[arg-type]
        semantic_planner=StaticPlanner(  # type: ignore[arg-type]
            _outcome(_external_plan(url="https://example.com/status"))
        ),
    )

    result = agent.run_with_steps("Read https://example.com/status")

    assert verifier.frames[0].explicit_url == "https://example.com/status"
    assert "cannot be read" in result["response"]
    assert engine.execute_calls == 0
    assert model.assess_calls == 0
    assert (
        result["execution_trace"]["runtime_metrics"]["semantic_loop"][
            "actual_tool_calls"
        ]
        == 0
    )


def test_semantic_url_literal_with_no_fetch_remains_content_only() -> None:
    verifier = FakeExternalVerifier(
        ExternalVerificationOutcome(failures=("must not fetch",)),
        [],
    )
    engine = ExternalLoopExecutionEngine()
    model = LoopAssessmentModel()
    planner = StaticPlanner(_outcome(_content_literal_plan()))
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        external_verifier=verifier,  # type: ignore[arg-type]
        semantic_planner=planner,  # type: ignore[arg-type]
    )

    result = agent.run_with_steps(
        "Write a config referencing https://example.com/app.tar.gz, but do not fetch it."
    )

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert planner.calls == 1
    assert verifier.frames == []
    assert engine.execute_calls == 0
    assert model.assess_calls == 0
    assert semantic["terminal_state"] == "DONE"
    assert semantic["actual_tool_calls"] == 0


@pytest.mark.parametrize(
    ("plan", "field"),
    (
        (
            replace(
                _direct_plan(),
                source_constraints=(SourceConstraint.URL_ONLY,),
                explicit_url="https://example.com/status",
            ),
            "request.route",
        ),
        (
            replace(
                _external_plan(url="https://example.com/status"),
                domain=RequestDomain.GENERAL,
            ),
            "request.domain",
        ),
    ),
)
def test_semantic_explicit_url_bypass_plan_never_reaches_model_memory(
    plan: SemanticPlan,
    field: str,
) -> None:
    verifier = FakeExternalVerifier(
        ExternalVerificationOutcome(failures=("fetch unavailable",)),
        [],
    )
    engine = ExternalLoopExecutionEngine()
    model = LoopAssessmentModel()
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        external_verifier=verifier,  # type: ignore[arg-type]
        semantic_planner=StaticPlanner(_outcome(plan)),  # type: ignore[arg-type]
    )

    result = agent.run_with_steps("Read https://example.com/status")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert verifier.frames == []
    assert model.assess_calls == 0
    assert engine.execute_calls == 0
    assert semantic["failure_detail"] == "request_conflict"
    assert semantic["validation"]["values"][0]["field"] == field


def test_unrelated_semantic_chat_does_not_mutate_infrastructure_context(
    tmp_path,
) -> None:
    store = ConversationStore("semantic-context", store_dir=str(tmp_path))
    original = SessionInvestigationContext(
        active_target="monitor",
        active_concept="cpu",
        active_sources=(SourceConstraint.GRAFANA,),
    )
    store.set_investigation_context(original)
    agent = DeterministicAgent(
        AgentLoopExecutionEngine(),  # type: ignore[arg-type]
        LoopAssessmentModel(),
        conversation_store=store,
        semantic_planner=StaticPlanner(_outcome(_direct_plan())),  # type: ignore[arg-type]
    )

    result = agent.run_with_steps("Hello there")

    assert result["response"] == "Hello."
    assert store.investigation_context == original
