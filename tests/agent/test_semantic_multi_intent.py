from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

import pytest

from src.agent.semantic_loop_coordinator import (
    SemanticLoopCoordinator,
    SemanticLoopResponse,
)
from src.model.semantic_planner_adapter import (
    SemanticPlannerOutcome,
    SemanticPlannerOutcomeReason,
    SemanticPlannerOutcomeStatus,
)
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.execution_runtime import RuntimeMetrics
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.request_frame import RequestFrame
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    MAX_SEMANTIC_SUBPLANS,
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
    SemanticSubplan,
    TargetReference,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_binding import (
    BoundSemanticCapability,
    SemanticPlanBindingResult,
)
from src.pipeline.semantic_plan_harness import SemanticPlanHarnessResult
from src.pipeline.semantic_plan_validation import SemanticPlanValidationResult
from src.pipeline.semantic_plan_wire import (
    SemanticPlanWireError,
    semantic_plan_from_wire,
    semantic_plan_to_wire,
)


def _direct(concept: str = "explanation") -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        concept=concept,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _capability(concept: str = "cpu") -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.ENVIRONMENT,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        target=TargetReference(TargetReferenceKind.EXPLICIT, "localhost"),
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.CURRENT,
        concept=concept,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _multi(*subplans: SemanticSubplan) -> SemanticPlan:
    return SemanticPlan(route=SemanticPlanRoute.MULTI_INTENT, subplans=tuple(subplans))


def test_multi_intent_wire_round_trip_preserves_separate_semantics() -> None:
    plan = _multi(
        SemanticSubplan("Explain RAM.", _direct("ram")),
        SemanticSubplan("Check CPU on localhost.", _capability("cpu")),
    )

    wire = semantic_plan_to_wire(plan)
    parsed = semantic_plan_from_wire(wire)

    assert parsed == plan
    assert wire["r"] == "multi_intent"
    assert len(wire["sp"]) == 2
    assert wire["sp"][0]["p"]["s"] == ["any"]
    assert wire["sp"][1]["p"]["t"] == {"k": "explicit", "v": "localhost"}
    assert wire["sp"][1]["p"]["f"] == "current"


def test_pre_subplan_v1_payload_without_sp_still_parses() -> None:
    plan = _direct("legacy")
    wire = semantic_plan_to_wire(plan)
    wire.pop("sp")

    assert semantic_plan_from_wire(wire) == plan


def test_multi_intent_children_require_explicit_source_and_freshness() -> None:
    unspecified_source = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        freshness=FreshnessRequirement.STABLE,
        concept="source",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )
    unknown_freshness = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.UNKNOWN,
        concept="freshness",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    for child in (unspecified_source, unknown_freshness):
        plan = _multi(
            SemanticSubplan("first", _direct()),
            SemanticSubplan("second", child),
        )
        with pytest.raises(SemanticPlanWireError):
            semantic_plan_to_wire(plan)


def test_multi_intent_is_bounded_non_recursive_and_acyclic() -> None:
    too_many = _multi(
        *(
            SemanticSubplan(f"task {index}", _direct(str(index)))
            for index in range(MAX_SEMANTIC_SUBPLANS + 1)
        )
    )
    with pytest.raises(SemanticPlanWireError, match="2-4"):
        semantic_plan_to_wire(too_many)

    nested = _multi(
        SemanticSubplan("first", _direct()),
        SemanticSubplan(
            "nested",
            _multi(SemanticSubplan("a", _direct()), SemanticSubplan("b", _direct())),
        ),
    )
    with pytest.raises(SemanticPlanWireError, match="Nested"):
        semantic_plan_to_wire(nested)

    forward_dependency = _multi(
        SemanticSubplan("first", _direct(), depends_on=(1,)),
        SemanticSubplan("second", _direct()),
    )
    with pytest.raises(SemanticPlanWireError, match="earlier"):
        semantic_plan_to_wire(forward_dependency)


def test_multi_intent_environment_child_requires_explicit_target() -> None:
    implicit = _capability()
    implicit = SemanticPlan(
        route=implicit.route,
        domain=implicit.domain,
        execution_intent=implicit.execution_intent,
        source_constraints=implicit.source_constraints,
        freshness=implicit.freshness,
        concept=implicit.concept,
        deterministic_compute=implicit.deterministic_compute,
        clarification=implicit.clarification,
    )
    plan = _multi(
        SemanticSubplan("Explain CPU.", _direct("cpu")),
        SemanticSubplan("Check CPU.", implicit),
    )
    with pytest.raises(SemanticPlanWireError, match="explicit target"):
        semantic_plan_to_wire(plan)


def test_harness_validates_each_subplan_without_implicit_target_inheritance() -> None:
    from src.pipeline.semantic_plan_harness import SemanticPlanHarnessValidator
    from src.pipeline.target_resolver import TargetResolver
    from src.tool.knowledge_tool import KnowledgeTool
    from src.tool.target_registry import TargetRegistry

    registry = TargetRegistry()
    registry.add("localhost")
    validator = SemanticPlanHarnessValidator(
        TargetResolver(registry), KnowledgeTool(registry)
    )
    plan = _multi(
        SemanticSubplan("Explain RAM.", _direct("ram")),
        SemanticSubplan("Check CPU on localhost.", _capability("cpu")),
    )

    result = validator.validate(plan, raw_request="multi")

    assert result.validation.can_execute
    assert len(result.subplans) == 2
    assert result.subplans[0].resolved_target is None
    assert result.subplans[1].resolved_target == "localhost"

@dataclass
class StaticPlanner:
    plan: SemanticPlan
    calls: int = 0

    def plan_safely(self, raw_request, *, context=None, request_id=None):
        self.calls += 1
        return SemanticPlannerOutcome(
            status=SemanticPlannerOutcomeStatus.VALID,
            reason=SemanticPlannerOutcomeReason.PLAN_VALID,
            plan=self.plan,
        )


class ValidatingStub:
    def validate(self, plan, *, raw_request):
        return SemanticPlanHarnessResult(SemanticPlanValidationResult.valid(plan))


class BindingStub:
    def bind(self, harness, *, raw_request, timeframe=None):
        plan = harness.validation.validated_plan
        assert plan is not None
        frame = RequestFrame(
            raw_request=raw_request,
            concepts=((plan.concept,) if plan.concept else ()),
            target_raw=plan.target.value,
            target_resolved=plan.target.value,
            request_domain=plan.domain,
            source_constraints=plan.source_constraints,
            execution_intent=plan.execution_intent,
        )
        request = InvestigationRequest(
            raw_request=raw_request,
            target=plan.target.value,
            request_frame=frame,
        )
        capability = BoundSemanticCapability(
            reference=CapabilityReference(
                name="CPU",
                evidence_name="CPU Usage",
                required=True,
                estimated_cost=0.1,
            ),
            source="localhost",
            resource="cpu",
            arguments=MappingProxyType({"source": "localhost", "resource": "cpu"}),
        )
        return SemanticPlanBindingResult(
            validation=SemanticPlanValidationResult.valid(plan),
            request=request,
            capabilities=(capability,),
            freshness=plan.freshness,
        )


def _response(text: str, *, model_used: bool = False) -> SemanticLoopResponse:
    return SemanticLoopResponse(
        text=text,
        answer_strategy="LLM_ASSESSMENT" if model_used else "DETERMINISTIC_TEMPLATE",
        model_used=model_used,
        postcondition_validation={"passed": True, "violations": []},
    )


def test_coordinator_executes_mixed_subplans_without_recursive_planner_calls() -> None:
    plan = _multi(
        SemanticSubplan("Explain RAM.", _direct("ram")),
        SemanticSubplan("Check CPU on localhost.", _capability("cpu")),
    )
    planner = StaticPlanner(plan)
    execute_calls = 0

    def execute(frame: RequestFrame) -> InvestigationRequest:
        nonlocal execute_calls
        execute_calls += 1
        return InvestigationRequest(
            raw_request=frame.raw_request,
            target=frame.target_resolved,
            request_frame=frame,
            runtime_metrics=RuntimeMetrics(tool_calls=1),
            evidence_complete=True,
        )

    result = SemanticLoopCoordinator(
        planner=planner,
        validator=ValidatingStub(),
        binder_factory=BindingStub,
        execute=execute,
        respond_direct=lambda request, _context: _response(
            f"direct:{request}", model_used=True
        ),
        respond_assessment=lambda request, _investigation: _response(
            f"assessed:{request}", model_used=True
        ),
        respond_failure=lambda _request, _failure, _detail: _response("failed"),
    ).run("Explain RAM then check CPU on localhost.")

    assert result.succeeded
    assert planner.calls == 1
    assert execute_calls == 1
    assert len(result.subplan_results) == 2
    assert result.response.text == (
        "[1] direct:Explain RAM.\n\n"
        "[2] assessed:Check CPU on localhost."
    )
    assert result.to_trace_dict()["final_response_count"] == 1
    assert len(result.to_trace_dict()["subplans"]) == 2


def test_dependency_context_is_explicit_and_independent_children_do_not_inherit() -> None:
    seen: list[str] = []
    plan = _multi(
        SemanticSubplan("Resolve version.", _direct("version")),
        SemanticSubplan("Independent explanation.", _direct("independent")),
        SemanticSubplan("Generate config using it.", _direct("config"), depends_on=(0,)),
    )

    def direct(request: str, _context) -> SemanticLoopResponse:
        seen.append(request)
        if request == "Resolve version.":
            return _response("version=2.0", model_used=True)
        return _response("ok", model_used=True)

    result = SemanticLoopCoordinator(
        planner=StaticPlanner(plan),
        validator=ValidatingStub(),
        binder_factory=BindingStub,
        execute=lambda _frame: pytest.fail("direct subplans must not execute tools"),
        respond_direct=direct,
        respond_assessment=lambda _request, _investigation: _response("unused"),
        respond_failure=lambda _request, _failure, _detail: _response("failed"),
    ).run("multi")

    assert result.succeeded
    assert seen[1] == "Independent explanation."
    assert "version=2.0" not in seen[1]
    assert seen[2].startswith(
        "Generate config using it.\n\nValidated prerequisite results"
    )
    assert "[1] version=2.0" in seen[2]
