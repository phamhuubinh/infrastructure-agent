from __future__ import annotations

from src.model.semantic_planner_adapter import (
    PlannerProviderRequest,
    PlannerProviderResponse,
    SemanticPlannerAdapter,
    SemanticPlannerOutcomeReason,
    SemanticPlannerOutcomeStatus,
)
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    SemanticPlan,
    SemanticPlanRoute,
    TargetReference,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_wire import semantic_plan_to_wire


class _Provider:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requests: list[PlannerProviderRequest] = []

    def generate_structured(
        self, request: PlannerProviderRequest
    ) -> PlannerProviderResponse:
        self.requests.append(request)
        return PlannerProviderResponse(
            payload=self.payload,
            provider="planner",
            model="semantic",
        )


def _plan(**changes: object) -> SemanticPlan:
    values: dict[str, object] = {
        "route": SemanticPlanRoute.DIRECT_ANSWER,
        "domain": RequestDomain.GENERAL,
        "execution_intent": ExecutionIntent.EXPLAIN,
        "source_constraints": (SourceConstraint.ANY,),
        "deterministic_compute": DeterministicComputeIntent.NOT_REQUIRED,
        "clarification": ClarificationState.NOT_REQUIRED,
    }
    values.update(changes)
    return SemanticPlan(**values)  # type: ignore[arg-type]


def test_malformed_output_is_a_non_dispatchable_structured_failure() -> None:
    valid = semantic_plan_to_wire(_plan())
    valid.pop("r")
    provider = _Provider(valid)

    outcome = SemanticPlannerAdapter([provider]).plan_safely("hello")

    assert outcome.status is SemanticPlannerOutcomeStatus.FAILED
    assert outcome.reason is SemanticPlannerOutcomeReason.MALFORMED_OUTPUT
    assert outcome.plan is None
    assert not outcome.can_dispatch
    assert len(provider.requests) == 1
    assert outcome.to_trace_dict()["reason"] == "malformed_output"


def test_missing_target_becomes_one_bounded_clarification() -> None:
    provider = _Provider(
        semantic_plan_to_wire(
            _plan(
                route=SemanticPlanRoute.CAPABILITY_ASSISTED,
                domain=RequestDomain.ENVIRONMENT,
                execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
            )
        )
    )

    outcome = SemanticPlannerAdapter([provider]).plan_safely("check RAM")

    assert outcome.status is SemanticPlannerOutcomeStatus.CLARIFY
    assert outcome.reason is SemanticPlannerOutcomeReason.INCOMPLETE_PLAN
    assert outcome.clarification_field == "target"
    assert not outcome.can_dispatch
    assert len(provider.requests) == 1


def test_ambiguous_target_and_unknown_semantics_never_guess_localhost() -> None:
    ambiguous = _Provider(
        semantic_plan_to_wire(
            _plan(
                route=SemanticPlanRoute.CAPABILITY_ASSISTED,
                domain=RequestDomain.ENVIRONMENT,
                execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
                target=TargetReference(TargetReferenceKind.AMBIGUOUS, None),
            )
        )
    )
    uncertain = _Provider(semantic_plan_to_wire(_plan(domain=RequestDomain.UNKNOWN)))

    clarification = SemanticPlannerAdapter([ambiguous]).plan_safely("máy kia")
    unsupported = SemanticPlannerAdapter([uncertain]).plan_safely("something")

    assert clarification.reason is SemanticPlannerOutcomeReason.AMBIGUOUS_TARGET
    assert clarification.clarification_field == "target"
    assert unsupported.status is SemanticPlannerOutcomeStatus.UNSUPPORTED
    assert unsupported.plan is None
    assert "localhost" not in str(clarification.to_trace_dict())
    assert "localhost" not in str(unsupported.to_trace_dict())


def test_contradictory_direct_execution_is_not_a_valid_plan() -> None:
    provider = _Provider(
        semantic_plan_to_wire(
            _plan(execution_intent=ExecutionIntent.MUTATE_ENVIRONMENT)
        )
    )

    outcome = SemanticPlannerAdapter([provider]).plan_safely("restart it")

    assert outcome.status is SemanticPlannerOutcomeStatus.FAILED
    assert outcome.reason is SemanticPlannerOutcomeReason.CONTRADICTORY_PLAN
    assert outcome.plan is None


def test_targetless_external_capability_plan_does_not_invent_target() -> None:
    plan = _plan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.EXTERNAL_INFORMATION,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        source_constraints=(SourceConstraint.INTERNET,),
    )

    outcome = SemanticPlannerAdapter(
        [_Provider(semantic_plan_to_wire(plan))]
    ).plan_safely("latest public release")

    assert outcome.status is SemanticPlannerOutcomeStatus.VALID
    assert outcome.plan == plan
    assert outcome.plan.target.value is None


def test_valid_semantics_are_the_only_dispatchable_outcome() -> None:
    plan = _plan(concept="greeting")
    outcome = SemanticPlannerAdapter(
        [_Provider(semantic_plan_to_wire(plan))]
    ).plan_safely("hello")

    assert outcome.status is SemanticPlannerOutcomeStatus.VALID
    assert outcome.plan == plan
    assert outcome.can_dispatch
