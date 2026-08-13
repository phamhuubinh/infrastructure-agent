from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

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


def test_defaults_are_explicit_and_non_executable() -> None:
    plan = SemanticPlan()

    assert plan.route is SemanticPlanRoute.UNSPECIFIED
    assert plan.domain is RequestDomain.UNSPECIFIED
    assert plan.execution_intent is ExecutionIntent.UNSPECIFIED
    assert plan.target == TargetReference()
    assert plan.target.kind is TargetReferenceKind.UNSPECIFIED
    assert plan.target.value is None
    assert plan.source_constraints == (SourceConstraint.UNSPECIFIED,)
    assert plan.freshness is FreshnessRequirement.UNSPECIFIED
    assert plan.deterministic_compute is DeterministicComputeIntent.UNSPECIFIED
    assert plan.clarification is ClarificationState.UNSPECIFIED


def test_representative_semantic_plans_are_typed_and_comparable() -> None:
    greeting = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        concept="greeting",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )
    cpu_inspection = SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.ENVIRONMENT,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        target=TargetReference(TargetReferenceKind.EXPLICIT, "monitor"),
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.REAL_TIME,
        metric="cpu.usage_percent",
        concept="cpu",
        clarification=ClarificationState.NOT_REQUIRED,
    )
    grafana_only = SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.ENVIRONMENT,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        target=TargetReference(TargetReferenceKind.EXPLICIT, "monitor"),
        source_constraints=(SourceConstraint.GRAFANA,),
        freshness=FreshnessRequirement.REAL_TIME,
        metric="cpu.usage_percent",
        concept="cpu",
        clarification=ClarificationState.NOT_REQUIRED,
    )
    current_web_fact = SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.EXTERNAL_INFORMATION,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.CURRENT,
        concept="python_version",
        clarification=ClarificationState.NOT_REQUIRED,
    )
    arithmetic = SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        concept="arithmetic",
        deterministic_compute=DeterministicComputeIntent.REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )
    mutation = SemanticPlan(
        route=SemanticPlanRoute.REFUSE,
        domain=RequestDomain.ACTION,
        execution_intent=ExecutionIntent.MUTATE_ENVIRONMENT,
        service="nginx",
        clarification=ClarificationState.NOT_REQUIRED,
    )
    clarification = SemanticPlan(
        route=SemanticPlanRoute.CLARIFY,
        domain=RequestDomain.UNKNOWN,
        execution_intent=ExecutionIntent.UNKNOWN,
        target=TargetReference(TargetReferenceKind.AMBIGUOUS, "server"),
        clarification=ClarificationState.REQUIRED,
        clarification_field="target",
    )

    assert greeting == SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        concept="greeting",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )
    assert (
        len(
            {
                greeting,
                cpu_inspection,
                grafana_only,
                current_web_fact,
                arithmetic,
                mutation,
                clarification,
            }
        )
        == 7
    )
    assert grafana_only.source_constraints == (SourceConstraint.GRAFANA,)
    assert current_web_fact.freshness is FreshnessRequirement.CURRENT
    assert arithmetic.deterministic_compute is DeterministicComputeIntent.REQUIRED
    assert mutation.execution_intent is ExecutionIntent.MUTATE_ENVIRONMENT
    assert clarification.clarification is ClarificationState.REQUIRED


def test_semantic_plan_and_target_reference_are_immutable() -> None:
    plan = SemanticPlan(
        target=TargetReference(TargetReferenceKind.EXPLICIT, "monitor"),
        metric="cpu.usage_percent",
    )

    with pytest.raises(FrozenInstanceError):
        plan.metric = "memory.usage_percent"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.target.value = "localhost"  # type: ignore[misc]
