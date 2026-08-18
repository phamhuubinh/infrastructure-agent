"""Bounded semantic plan-to-response coordinator.

The coordinator owns the only transition that may call the execution engine.
Planner and response callbacks receive no tool handle.  Trace output contains
only state and reason codes, never model prompts, hidden reasoning, evidence
payloads, or exception messages.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from src.model.protocol.semantic_planner_prompt import PlannerPromptContext
from src.model.semantic_planner_adapter import (
    SemanticPlannerOutcome,
    SemanticPlannerOutcomeStatus,
)
from src.pipeline.basic_calculator import (
    CalculatorContractResult,
    CalculatorRequest,
    calculate_request,
)
from src.pipeline.execution_budget import ExecutionBudget, ExecutionBudgetConfig
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.request_frame import RequestFrame
from src.pipeline.semantic_plan import SemanticPlan, SemanticPlanRoute
from src.pipeline.semantic_plan_binding import (
    SemanticPlanBindingResult,
)
from src.pipeline.semantic_plan_harness import (
    SemanticPlanHarnessResult,
    planner_final_answer_allowed,
)
from src.pipeline.semantic_plan_validation import SemanticPlanValidationStatus
from src.pipeline.time_range_resolver import TimeRange


class SemanticLoopState(str, Enum):
    PLAN = "PLAN"
    VALIDATE = "VALIDATE"
    EXECUTE = "EXECUTE"
    ASSESS_RESPOND = "ASSESS/RESPOND"
    DONE = "DONE"
    FAIL = "FAIL"


class SemanticLoopFailure(str, Enum):
    PLANNER_CLARIFICATION = "planner_clarification"
    PLANNER_UNSUPPORTED = "planner_unsupported"
    PROVIDER_FAILURE = "provider_failure"
    VALIDATION_FAILED = "validation_failed"
    BINDING_FAILED = "binding_failed"
    UNSUPPORTED_ROUTE = "unsupported_route"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXECUTION_FAILED = "execution_failed"
    RESPONSE_FAILED = "response_failed"
    CALCULATION_FAILED = "calculation_failed"
    STATE_LIMIT = "state_limit"


class SemanticLoopRecordStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class SemanticLoopStateRecord:
    state: SemanticLoopState
    status: SemanticLoopRecordStatus
    reason: str
    duration_ms: float = 0.0

    def to_trace_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "status": self.status.value,
            "reason": self.reason,
            "duration_ms": round(max(self.duration_ms, 0.0), 3),
        }


@dataclass(frozen=True, slots=True)
class SemanticLoopResponse:
    text: str
    answer_strategy: str
    model_used: bool
    artifact_validation: dict[str, object] | None = None
    postcondition_validation: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Semantic loop response must be non-empty text.")
        if not isinstance(self.answer_strategy, str) or not self.answer_strategy:
            raise ValueError("answer_strategy must be non-empty text.")


@dataclass(frozen=True, slots=True)
class SemanticLoopConfig:
    max_state_transitions: int = 6
    execution_budget: ExecutionBudgetConfig = field(
        default_factory=ExecutionBudgetConfig
    )

    def __post_init__(self) -> None:
        if self.max_state_transitions < 2 or self.max_state_transitions > 16:
            raise ValueError("max_state_transitions must be between 2 and 16.")


@dataclass(frozen=True, slots=True)
class SemanticLoopResult:
    terminal_state: SemanticLoopState
    response: SemanticLoopResponse
    records: tuple[SemanticLoopStateRecord, ...]
    planner_outcome: SemanticPlannerOutcome | None = None
    harness: SemanticPlanHarnessResult | None = None
    binding: SemanticPlanBindingResult | None = None
    investigation: InvestigationRequest | None = None
    failure: SemanticLoopFailure | None = None
    failure_detail: str | None = None
    execution_cycles: int = 0
    planned_tool_calls: int = 0
    actual_tool_calls: int = 0
    calculator_calls: int = 0
    calculation: CalculatorContractResult | None = None
    budget: ExecutionBudget | None = None

    @property
    def succeeded(self) -> bool:
        return self.terminal_state is SemanticLoopState.DONE

    def to_trace_dict(self) -> dict[str, object]:
        trace: dict[str, object] = {
            "terminal_state": self.terminal_state.value,
            "succeeded": self.succeeded,
            "state_history": [record.state.value for record in self.records],
            "states": [record.to_trace_dict() for record in self.records],
            "execution_cycles": self.execution_cycles,
            "planned_tool_calls": self.planned_tool_calls,
            "actual_tool_calls": self.actual_tool_calls,
            "calculator_calls": self.calculator_calls,
            "final_response_count": 1,
            "failure": self.failure.value if self.failure is not None else None,
            "failure_detail": self.failure_detail,
            "budget": self.budget.to_dict() if self.budget is not None else None,
        }
        if self.planner_outcome is not None:
            trace["planner"] = self.planner_outcome.to_trace_dict()
        if self.harness is not None:
            trace["validation"] = self.harness.to_trace_dict()
        if self.binding is not None:
            trace["binding"] = self.binding.to_trace_dict()
        if self.calculation is not None:
            trace["calculator"] = {
                "status": self.calculation.status.value,
                "operation": (
                    self.calculation.operation.value
                    if self.calculation.operation is not None
                    else None
                ),
                "unit": self.calculation.unit,
            }
        postconditions = _bounded_postcondition_trace(
            self.response.postcondition_validation
        )
        if postconditions is not None:
            trace["postconditions"] = postconditions
        return trace


class SemanticPlannerProtocol(Protocol):
    def plan_safely(
        self,
        raw_request: str,
        *,
        context: PlannerPromptContext | None = None,
        request_id: str | None = None,
    ) -> SemanticPlannerOutcome: ...


class SemanticValidatorProtocol(Protocol):
    def validate(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
    ) -> SemanticPlanHarnessResult: ...


class SemanticBinderProtocol(Protocol):
    def bind(
        self,
        harness: SemanticPlanHarnessResult,
        *,
        raw_request: str,
        timeframe: TimeRange | None = None,
    ) -> SemanticPlanBindingResult: ...


BinderFactory = Callable[[], SemanticBinderProtocol]
ExecuteCallback = Callable[[RequestFrame], InvestigationRequest]
DirectResponseCallback = Callable[
    [str, PlannerPromptContext | None], SemanticLoopResponse
]
PlannerAnswerCallback = Callable[[str, str], SemanticLoopResponse]
AssessmentResponseCallback = Callable[[str, InvestigationRequest], SemanticLoopResponse]
ComputeCallback = Callable[[CalculatorRequest], CalculatorContractResult]
ComputeResponseCallback = Callable[
    [str, SemanticPlan, CalculatorContractResult], SemanticLoopResponse
]
FailureResponseCallback = Callable[
    [str, SemanticLoopFailure, str | None], SemanticLoopResponse
]
ResponseVerifierCallback = Callable[
    [
        str,
        SemanticLoopResponse,
        SemanticPlan,
        SemanticPlanHarnessResult,
        InvestigationRequest | None,
        CalculatorContractResult | None,
    ],
    SemanticLoopResponse,
]


class SemanticLoopCoordinator:
    """Run one finite semantic cycle with no planner-controlled retry path."""

    def __init__(
        self,
        *,
        planner: SemanticPlannerProtocol,
        validator: SemanticValidatorProtocol,
        binder_factory: BinderFactory,
        execute: ExecuteCallback,
        respond_direct: DirectResponseCallback,
        respond_assessment: AssessmentResponseCallback,
        respond_failure: FailureResponseCallback,
        compute: ComputeCallback = calculate_request,
        respond_compute: ComputeResponseCallback | None = None,
        verify_response: ResponseVerifierCallback | None = None,
        accept_planner_answer: PlannerAnswerCallback | None = None,
        config: SemanticLoopConfig | None = None,
    ) -> None:
        self._planner = planner
        self._validator = validator
        self._binder_factory = binder_factory
        self._execute = execute
        self._respond_direct = respond_direct
        self._respond_assessment = respond_assessment
        self._respond_failure = respond_failure
        self._compute = compute
        self._respond_compute = respond_compute
        self._verify_response = verify_response
        self._accept_planner_answer = accept_planner_answer
        self._config = config or SemanticLoopConfig()

    def run(
        self,
        raw_request: str,
        *,
        context: PlannerPromptContext | None = None,
        timeframe: TimeRange | None = None,
    ) -> SemanticLoopResult:
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("raw_request must be non-empty text.")

        state = SemanticLoopState.PLAN
        records: list[SemanticLoopStateRecord] = []
        planner_outcome: SemanticPlannerOutcome | None = None
        harness: SemanticPlanHarnessResult | None = None
        binding: SemanticPlanBindingResult | None = None
        investigation: InvestigationRequest | None = None
        response: SemanticLoopResponse | None = None
        failure: SemanticLoopFailure | None = None
        failure_detail: str | None = None
        execution_cycles = 0
        planned_tool_calls = 0
        actual_tool_calls = 0
        calculator_calls = 0
        calculation: CalculatorContractResult | None = None
        budget: ExecutionBudget | None = None
        planner_final_answer: str | None = None
        use_planner_answer = False

        for _transition in range(self._config.max_state_transitions):
            started = time.perf_counter()
            if state is SemanticLoopState.PLAN:
                try:
                    planner_outcome = self._planner.plan_safely(
                        raw_request,
                        context=context,
                    )
                    if not isinstance(planner_outcome, SemanticPlannerOutcome):
                        raise TypeError("planner outcome contract is invalid")
                except Exception as exc:
                    failure = SemanticLoopFailure.PROVIDER_FAILURE
                    failure_detail = type(exc).__name__
                    records.append(_record(state, False, failure.value, started))
                    state = SemanticLoopState.FAIL
                    continue
                if planner_outcome.status is not SemanticPlannerOutcomeStatus.VALID:
                    failure = _planner_failure(planner_outcome.status)
                    failure_detail = planner_outcome.reason.value
                    records.append(_record(state, False, failure_detail, started))
                    state = SemanticLoopState.FAIL
                    continue
                planner_result = planner_outcome.result
                planner_final_answer = (
                    planner_result.final_answer if planner_result is not None else None
                )
                records.append(_record(state, True, "plan_valid", started))
                state = SemanticLoopState.VALIDATE
                continue

            if state is SemanticLoopState.VALIDATE:
                plan = planner_outcome.plan if planner_outcome is not None else None
                if plan is None:
                    failure = SemanticLoopFailure.VALIDATION_FAILED
                    failure_detail = "plan_missing"
                    records.append(_record(state, False, failure_detail, started))
                    state = SemanticLoopState.FAIL
                    continue
                try:
                    harness = self._validator.validate(
                        plan,
                        raw_request=raw_request,
                    )
                except Exception as exc:
                    failure = SemanticLoopFailure.VALIDATION_FAILED
                    failure_detail = type(exc).__name__
                    records.append(_record(state, False, failure.value, started))
                    state = SemanticLoopState.FAIL
                    continue
                if harness.validation.status is not SemanticPlanValidationStatus.VALID:
                    failure = SemanticLoopFailure.VALIDATION_FAILED
                    failure_detail = harness.validation.reason.value
                    records.append(_record(state, False, failure_detail, started))
                    state = SemanticLoopState.FAIL
                    continue
                if plan.route is SemanticPlanRoute.DIRECT_ANSWER:
                    if plan.calculation is not None:
                        records.append(
                            _record(state, True, "calculator_bound", started)
                        )
                        state = SemanticLoopState.EXECUTE
                    elif (
                        self._accept_planner_answer is not None
                        and planner_final_answer is not None
                        and planner_final_answer_allowed(plan)
                    ):
                        use_planner_answer = True
                        records.append(_record(state, True, "planner_answer", started))
                        state = SemanticLoopState.ASSESS_RESPOND
                    else:
                        records.append(_record(state, True, "direct_answer", started))
                        state = SemanticLoopState.ASSESS_RESPOND
                    continue
                if plan.route is not SemanticPlanRoute.CAPABILITY_ASSISTED:
                    failure = SemanticLoopFailure.UNSUPPORTED_ROUTE
                    failure_detail = plan.route.value
                    records.append(_record(state, False, failure_detail, started))
                    state = SemanticLoopState.FAIL
                    continue

                try:
                    binding = self._binder_factory().bind(
                        harness,
                        raw_request=raw_request,
                        timeframe=timeframe,
                    )
                    if not isinstance(binding, SemanticPlanBindingResult):
                        raise TypeError("binding result contract is invalid")
                except Exception as exc:
                    failure = SemanticLoopFailure.BINDING_FAILED
                    failure_detail = type(exc).__name__
                    records.append(_record(state, False, failure.value, started))
                    state = SemanticLoopState.FAIL
                    continue
                if not binding.bound:
                    failure = SemanticLoopFailure.BINDING_FAILED
                    failure_detail = binding.validation.reason.value
                    records.append(_record(state, False, failure_detail, started))
                    state = SemanticLoopState.FAIL
                    continue

                planned_tool_calls = len(binding.capabilities)
                estimated_cost = sum(
                    item.reference.estimated_cost for item in binding.capabilities
                )
                budget = ExecutionBudget(self._config.execution_budget)
                if not budget.start_round(planned_tool_calls, estimated_cost):
                    failure = SemanticLoopFailure.BUDGET_EXHAUSTED
                    failure_detail = "pre_execution_budget"
                    records.append(_record(state, False, failure_detail, started))
                    state = SemanticLoopState.FAIL
                    continue
                records.append(_record(state, True, "bound", started))
                state = SemanticLoopState.EXECUTE
                continue

            if state is SemanticLoopState.EXECUTE:
                plan = planner_outcome.plan if planner_outcome is not None else None
                if plan is not None and plan.calculation is not None:
                    calculator_calls += 1
                    try:
                        calculation = self._compute(plan.calculation)
                        if not isinstance(calculation, CalculatorContractResult):
                            raise TypeError("calculator result contract is invalid")
                    except Exception as exc:
                        failure = SemanticLoopFailure.CALCULATION_FAILED
                        failure_detail = type(exc).__name__
                        records.append(_record(state, False, failure.value, started))
                        state = SemanticLoopState.FAIL
                        continue
                    if not calculation.ok:
                        failure = SemanticLoopFailure.CALCULATION_FAILED
                        failure_detail = calculation.reason or calculation.status.value
                        records.append(_record(state, False, failure_detail, started))
                        state = SemanticLoopState.FAIL
                        continue
                    records.append(_record(state, True, "calculated", started))
                    state = SemanticLoopState.ASSESS_RESPOND
                    continue
                frame = (
                    binding.request.request_frame
                    if binding is not None and binding.request is not None
                    else None
                )
                if frame is None:
                    failure = SemanticLoopFailure.EXECUTION_FAILED
                    failure_detail = "request_frame_missing"
                    records.append(_record(state, False, failure_detail, started))
                    state = SemanticLoopState.FAIL
                    continue
                execution_cycles += 1
                try:
                    investigation = self._execute(frame)
                    if not isinstance(investigation, InvestigationRequest):
                        raise TypeError("execution result contract is invalid")
                except Exception as exc:
                    failure = SemanticLoopFailure.EXECUTION_FAILED
                    failure_detail = type(exc).__name__
                    records.append(_record(state, False, failure.value, started))
                    state = SemanticLoopState.FAIL
                    continue
                actual_tool_calls = int(
                    getattr(investigation.runtime_metrics, "tool_calls", 0) or 0
                )
                engine_budget = investigation.execution_budget
                engine_rounds = engine_budget.rounds if engine_budget is not None else 1
                if (
                    actual_tool_calls > self._config.execution_budget.max_capabilities
                    or engine_rounds > self._config.execution_budget.max_rounds
                ):
                    failure = SemanticLoopFailure.BUDGET_EXHAUSTED
                    failure_detail = "execution_budget_violation"
                    records.append(_record(state, False, failure_detail, started))
                    state = SemanticLoopState.FAIL
                    continue
                if budget is not None:
                    budget.stop(
                        evidence_sufficient=investigation.evidence_complete,
                        recoverable_path=False,
                    )
                records.append(_record(state, True, "executed", started))
                state = SemanticLoopState.ASSESS_RESPOND
                continue

            if state is SemanticLoopState.ASSESS_RESPOND:
                try:
                    plan = (
                        planner_outcome.plan if planner_outcome is not None else None
                    )
                    if calculation is not None:
                        if plan is None or self._respond_compute is None:
                            raise TypeError("compute response callback is unavailable")
                        response = self._respond_compute(
                            raw_request,
                            plan,
                            calculation,
                        )
                    elif investigation is not None:
                        response = self._respond_assessment(raw_request, investigation)
                    elif use_planner_answer and planner_final_answer is not None:
                        response = self._accept_planner_answer(
                            raw_request,
                            planner_final_answer,
                        )
                    else:
                        response = self._respond_direct(raw_request, context)
                    if not isinstance(response, SemanticLoopResponse):
                        raise TypeError("response contract is invalid")
                    if self._verify_response is not None:
                        if plan is None or harness is None:
                            raise TypeError("response verification context is missing")
                        response = self._verify_response(
                            raw_request,
                            response,
                            plan,
                            harness,
                            investigation,
                            calculation,
                        )
                        if not isinstance(response, SemanticLoopResponse):
                            raise TypeError("verified response contract is invalid")
                except Exception as exc:
                    failure = SemanticLoopFailure.RESPONSE_FAILED
                    failure_detail = type(exc).__name__
                    records.append(_record(state, False, failure.value, started))
                    state = SemanticLoopState.FAIL
                    continue
                records.append(_record(state, True, "response_ready", started))
                state = SemanticLoopState.DONE
                continue

            if state is SemanticLoopState.DONE:
                records.append(_record(state, True, "complete", started))
                if response is None:
                    raise RuntimeError("DONE state requires a response.")
                return _result(
                    state,
                    response,
                    records,
                    planner_outcome,
                    harness,
                    binding,
                    investigation,
                    failure,
                    failure_detail,
                    execution_cycles,
                    planned_tool_calls,
                    actual_tool_calls,
                    budget,
                    calculator_calls,
                    calculation,
                )

            if state is SemanticLoopState.FAIL:
                response = self._safe_failure_response(
                    raw_request,
                    failure or SemanticLoopFailure.STATE_LIMIT,
                    failure_detail,
                )
                records.append(
                    _record(
                        state,
                        False,
                        (failure or SemanticLoopFailure.STATE_LIMIT).value,
                        started,
                    )
                )
                return _result(
                    state,
                    response,
                    records,
                    planner_outcome,
                    harness,
                    binding,
                    investigation,
                    failure or SemanticLoopFailure.STATE_LIMIT,
                    failure_detail,
                    execution_cycles,
                    planned_tool_calls,
                    actual_tool_calls,
                    budget,
                    calculator_calls,
                    calculation,
                )

        failure = SemanticLoopFailure.STATE_LIMIT
        failure_detail = "max_state_transitions"
        response = self._safe_failure_response(raw_request, failure, failure_detail)
        records.append(
            SemanticLoopStateRecord(
                state=SemanticLoopState.FAIL,
                status=SemanticLoopRecordStatus.FAILED,
                reason=failure.value,
            )
        )
        return _result(
            SemanticLoopState.FAIL,
            response,
            records,
            planner_outcome,
            harness,
            binding,
            investigation,
            failure,
            failure_detail,
            execution_cycles,
            planned_tool_calls,
            actual_tool_calls,
            budget,
            calculator_calls,
            calculation,
        )

    def _safe_failure_response(
        self,
        raw_request: str,
        failure: SemanticLoopFailure,
        detail: str | None,
    ) -> SemanticLoopResponse:
        try:
            response = self._respond_failure(raw_request, failure, detail)
            if not isinstance(response, SemanticLoopResponse):
                raise TypeError("failure response contract is invalid")
            return response
        except Exception:
            return SemanticLoopResponse(
                text="The bounded semantic loop stopped safely without further execution.",
                answer_strategy="REFUSAL",
                model_used=False,
            )


def _planner_failure(
    status: SemanticPlannerOutcomeStatus,
) -> SemanticLoopFailure:
    if status is SemanticPlannerOutcomeStatus.CLARIFY:
        return SemanticLoopFailure.PLANNER_CLARIFICATION
    if status is SemanticPlannerOutcomeStatus.UNSUPPORTED:
        return SemanticLoopFailure.PLANNER_UNSUPPORTED
    return SemanticLoopFailure.PROVIDER_FAILURE


def _bounded_postcondition_trace(
    value: dict[str, object] | None,
) -> dict[str, object] | None:
    """Expose only stable postcondition and relevance codes in loop traces."""

    if value is None:
        return None
    raw_violations = value.get("violations", ())
    violations = (
        [str(item)[:64] for item in raw_violations[:8]]
        if isinstance(raw_violations, (list, tuple))
        else []
    )
    trace: dict[str, object] = {
        "passed": bool(value.get("passed")),
        "violations": violations,
    }
    relevance = value.get("relevance")
    if isinstance(relevance, dict):
        decision = relevance.get("decision")
        reason = relevance.get("reason")
        if isinstance(decision, str) and isinstance(reason, str):
            trace["relevance"] = {
                "decision": decision[:32],
                "reason": reason[:64],
            }
    repair = value.get("repair")
    if isinstance(repair, dict):
        status = repair.get("status")
        if isinstance(status, str):
            trace["repair"] = {
                "attempted": bool(repair.get("attempted")),
                "status": status[:64],
            }
    return trace


def _record(
    state: SemanticLoopState,
    succeeded: bool,
    reason: str,
    started: float,
) -> SemanticLoopStateRecord:
    return SemanticLoopStateRecord(
        state=state,
        status=(
            SemanticLoopRecordStatus.SUCCEEDED
            if succeeded
            else SemanticLoopRecordStatus.FAILED
        ),
        reason=reason[:128],
        duration_ms=(time.perf_counter() - started) * 1000.0,
    )


def _result(
    terminal_state: SemanticLoopState,
    response: SemanticLoopResponse,
    records: list[SemanticLoopStateRecord],
    planner_outcome: SemanticPlannerOutcome | None,
    harness: SemanticPlanHarnessResult | None,
    binding: SemanticPlanBindingResult | None,
    investigation: InvestigationRequest | None,
    failure: SemanticLoopFailure | None,
    failure_detail: str | None,
    execution_cycles: int,
    planned_tool_calls: int,
    actual_tool_calls: int,
    budget: ExecutionBudget | None,
    calculator_calls: int,
    calculation: CalculatorContractResult | None,
) -> SemanticLoopResult:
    return SemanticLoopResult(
        terminal_state=terminal_state,
        response=response,
        records=tuple(records),
        planner_outcome=planner_outcome,
        harness=harness,
        binding=binding,
        investigation=investigation,
        failure=failure,
        failure_detail=(failure_detail[:128] if failure_detail else None),
        execution_cycles=execution_cycles,
        planned_tool_calls=planned_tool_calls,
        actual_tool_calls=actual_tool_calls,
        calculator_calls=calculator_calls,
        calculation=calculation,
        budget=budget,
    )


__all__ = [
    "SemanticLoopConfig",
    "SemanticLoopCoordinator",
    "SemanticLoopFailure",
    "SemanticLoopRecordStatus",
    "SemanticLoopResponse",
    "SemanticLoopResult",
    "SemanticLoopState",
    "SemanticLoopStateRecord",
]
