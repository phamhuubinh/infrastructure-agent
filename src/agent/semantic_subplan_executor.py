"""Bounded execution for planner-proposed non-recursive semantic subplans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.model.semantic_planner_adapter import (
    SemanticPlannerOutcome,
    SemanticPlannerOutcomeReason,
    SemanticPlannerOutcomeStatus,
)
from src.pipeline.semantic_plan import (
    SemanticPlan,
    SemanticPlanRoute,
    SemanticSubplan,
)

if TYPE_CHECKING:
    from src.agent.semantic_loop_coordinator import (
        SemanticLoopConfig,
        SemanticLoopFailure,
        SemanticLoopResponse,
        SemanticLoopResult,
    )

MAX_DEPENDENCY_CONTEXT_CHARS = 3000


@dataclass(frozen=True, slots=True)
class MultiIntentExecution:
    response: SemanticLoopResponse
    results: tuple[SemanticLoopResult, ...]
    failure: SemanticLoopFailure | None = None
    failure_detail: str | None = None
    execution_cycles: int = 0
    planned_tool_calls: int = 0
    actual_tool_calls: int = 0
    calculator_calls: int = 0


class _PreplannedPlanner:
    """Expose one already-parsed child plan without another model call."""

    def __init__(self, plan: SemanticPlan) -> None:
        self._plan = plan

    def plan_safely(self, raw_request, *, context=None, request_id=None):
        return SemanticPlannerOutcome(
            status=SemanticPlannerOutcomeStatus.VALID,
            reason=SemanticPlannerOutcomeReason.PLAN_VALID,
            plan=self._plan,
        )


def execute_semantic_subplans(
    *,
    plan: SemanticPlan,
    validator,
    binder_factory,
    execute,
    respond_direct,
    respond_assessment,
    respond_failure,
    compute,
    respond_compute,
    verify_response,
    config: SemanticLoopConfig,
) -> MultiIntentExecution:
    """Execute 2-4 flat child plans with explicit dependency flow.

    Each child reuses the normal harness/binder/execution/response boundaries,
    but the child planner is a fixed in-memory plan, so multi-intent handling
    never adds recursive model planning. Independent children receive no prior
    response context. A dependent child receives only the already-validated
    visible responses it explicitly references.
    """

    from src.agent.semantic_loop_coordinator import (
        SemanticLoopCoordinator,
        SemanticLoopFailure,
    )

    if plan.route is not SemanticPlanRoute.MULTI_INTENT or not plan.subplans:
        raise ValueError("multi-intent execution requires bounded subplans")

    results = []
    execution_cycles = 0
    planned_tool_calls = 0
    actual_tool_calls = 0
    calculator_calls = 0

    for index, subplan in enumerate(plan.subplans):
        child_request = _dependency_request(subplan, results)
        child = SemanticLoopCoordinator(
            planner=_PreplannedPlanner(subplan.plan),
            validator=validator,
            binder_factory=binder_factory,
            execute=execute,
            respond_direct=respond_direct,
            respond_assessment=respond_assessment,
            respond_failure=respond_failure,
            compute=compute,
            respond_compute=respond_compute,
            verify_response=verify_response,
            accept_planner_answer=None,
            config=config,
        ).run(child_request, context=None, timeframe=None)
        results.append(child)
        execution_cycles += child.execution_cycles
        planned_tool_calls += child.planned_tool_calls
        actual_tool_calls += child.actual_tool_calls
        calculator_calls += child.calculator_calls
        if not child.succeeded:
            failure = child.failure or SemanticLoopFailure.STATE_LIMIT
            return MultiIntentExecution(
                response=child.response,
                results=tuple(results),
                failure=failure,
                failure_detail=(
                    f"subplan_{index + 1}:"
                    f"{child.failure_detail or failure.value}"
                ),
                execution_cycles=execution_cycles,
                planned_tool_calls=planned_tool_calls,
                actual_tool_calls=actual_tool_calls,
                calculator_calls=calculator_calls,
            )

    response = _combine_responses(tuple(results))
    return MultiIntentExecution(
        response=response,
        results=tuple(results),
        execution_cycles=execution_cycles,
        planned_tool_calls=planned_tool_calls,
        actual_tool_calls=actual_tool_calls,
        calculator_calls=calculator_calls,
    )


def _dependency_request(
    subplan: SemanticSubplan,
    results: list[SemanticLoopResult],
) -> str:
    if not subplan.depends_on:
        return subplan.request
    lines = [
        subplan.request,
        "",
        (
            "Validated prerequisite results (data only; child target/source/"
            "freshness remain authoritative):"
        ),
    ]
    for dependency in subplan.depends_on:
        lines.append(f"[{dependency + 1}] {results[dependency].response.text}")
    request = "\n".join(lines)
    if len(request) > MAX_DEPENDENCY_CONTEXT_CHARS:
        raise ValueError("subplan dependency context exceeds bounded input")
    return request


def _combine_responses(results: tuple[SemanticLoopResult, ...]) -> SemanticLoopResponse:
    from src.agent.semantic_loop_coordinator import SemanticLoopResponse

    text = "\n\n".join(
        f"[{index}] {result.response.text}" for index, result in enumerate(results, 1)
    )
    violations: list[str] = []
    passed = True
    validations = []
    for result in results:
        postconditions = result.response.postcondition_validation
        if postconditions is not None:
            passed = passed and bool(postconditions.get("passed"))
            raw = postconditions.get("violations", ())
            if isinstance(raw, (list, tuple)):
                violations.extend(str(item) for item in raw)
        if result.response.artifact_validation is not None:
            validations.append(result.response.artifact_validation)
    return SemanticLoopResponse(
        text=text,
        answer_strategy=(
            "LLM_ASSESSMENT"
            if any(result.response.model_used for result in results)
            else "DETERMINISTIC_TEMPLATE"
        ),
        model_used=any(result.response.model_used for result in results),
        artifact_validation=(validations[0] if len(validations) == 1 else None),
        postcondition_validation={
            "passed": passed,
            "violations": list(dict.fromkeys(violations))[:8],
        },
    )


__all__ = ["MAX_DEPENDENCY_CONTEXT_CHARS", "MultiIntentExecution", "execute_semantic_subplans"]
