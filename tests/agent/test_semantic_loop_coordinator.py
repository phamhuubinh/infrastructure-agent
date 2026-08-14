from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType

from src.agent.deterministic_agent import DeterministicAgent
from src.agent.semantic_loop_coordinator import (
    SemanticLoopConfig,
    SemanticLoopCoordinator,
    SemanticLoopFailure,
    SemanticLoopResponse,
    SemanticLoopState,
)
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.semantic_planner_adapter import (
    SemanticPlannerOutcome,
    SemanticPlannerOutcomeReason,
    SemanticPlannerOutcomeStatus,
)
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.execution_budget import ExecutionBudget, ExecutionBudgetConfig
from src.pipeline.execution_runtime import RuntimeMetrics
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
    assert "SECRET_PROVIDER_DETAIL" not in json.dumps(
        response_result.to_trace_dict()
    )


class LoopAssessmentModel(AssessmentModelAdapter):
    def __init__(self) -> None:
        self.assess_calls = 0

    def assess(self, assessment_request: AssessmentRequest) -> str:
        self.assess_calls += 1
        return "Bounded assessment."


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
