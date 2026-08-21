from __future__ import annotations

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
from src.pipeline.semantic_plan_harness import SemanticPlanHarnessValidator
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationStatus,
)
from src.pipeline.semantic_request_consistency import (
    SemanticRequestConsistencyValidator,
)
from src.pipeline.target_resolver import TargetResolver
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


def _runtime() -> tuple[TargetResolver, KnowledgeTool]:
    registry = TargetRegistry()
    registry.add("localhost")
    registry.add("server01")
    registry.add("server02")
    return TargetResolver(registry), KnowledgeTool(registry)


def _environment_plan(
    *,
    target: str = "server01",
    source: SourceConstraint = SourceConstraint.GRAFANA,
    freshness: FreshnessRequirement = FreshnessRequirement.CURRENT,
) -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.ENVIRONMENT,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        target=TargetReference(TargetReferenceKind.EXPLICIT, target),
        source_constraints=(source,),
        freshness=freshness,
        concept="cpu",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def test_harness_rejects_planner_target_contradicting_original_request() -> None:
    resolver, knowledge = _runtime()
    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        _environment_plan(target="server02"),
        raw_request="Check CPU on server01",
    )

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.REQUEST_CONFLICT
    assert result.validation.values[0].field == "request.target"
    assert result.validation.values[0].original == "server01"
    assert result.validation.values[0].normalized == "server02"
    assert result.sources is None


def test_harness_rejects_planner_source_weakening_grafana_only() -> None:
    resolver, knowledge = _runtime()
    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        _environment_plan(source=SourceConstraint.ZABBIX),
        raw_request="Grafana only: check CPU on server01",
    )

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.REQUEST_CONFLICT
    assert result.validation.values[0].field == "request.source"
    assert result.validation.values[0].original == "GRAFANA"
    assert result.validation.values[0].normalized == "ZABBIX"
    assert result.sources is None


def test_harness_rejects_stable_plan_for_current_external_request() -> None:
    resolver, knowledge = _runtime()
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        plan,
        raw_request="What is the latest stable Python release?",
    )

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.REQUEST_CONFLICT
    assert result.validation.values[0].field == "request.freshness"
    assert result.sources is None


def test_harness_rejects_direct_general_downgrade_of_live_target_request() -> None:
    resolver, knowledge = _runtime()
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        plan,
        raw_request="check CPU on server01",
    )

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.REQUEST_CONFLICT
    assert result.validation.values[0].field == "request.target"
    assert result.sources is None


def test_harness_clarifies_unknown_raw_target_before_direct_plan_can_answer() -> None:
    resolver, knowledge = _runtime()
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        plan,
        raw_request="check RAM on ghost-host",
    )

    assert result.validation.status is SemanticPlanValidationStatus.CLARIFY
    assert result.validation.reason is SemanticPlanValidationReason.TARGET_UNKNOWN
    assert result.sources is None


def test_harness_rejects_stable_freshness_for_live_environment_request() -> None:
    resolver, knowledge = _runtime()
    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        _environment_plan(
            source=SourceConstraint.ANY,
            freshness=FreshnessRequirement.STABLE,
        ),
        raw_request="check CPU on server01",
    )

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.REQUEST_CONFLICT
    assert result.validation.values[0].field == "request.freshness"
    assert result.sources is None


def test_harness_rejects_general_domain_for_live_environment_request() -> None:
    resolver, knowledge = _runtime()
    plan = SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        target=TargetReference(TargetReferenceKind.EXPLICIT, "server01"),
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.CURRENT,
        concept="cpu",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        plan,
        raw_request="check CPU usage",
    )

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.REQUEST_CONFLICT
    assert result.validation.values[0].field == "request.domain"
    assert result.sources is None


def test_unknown_explicit_request_target_never_accepts_planner_localhost() -> None:
    resolver, knowledge = _runtime()
    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        _environment_plan(target="localhost", source=SourceConstraint.ANY),
        raw_request="Check CPU on doesnotexist123",
    )

    assert result.validation.status is SemanticPlanValidationStatus.CLARIFY
    assert result.validation.reason is SemanticPlanValidationReason.TARGET_UNKNOWN
    assert result.sources is None


def test_consistency_validator_allows_matching_stable_direct_request() -> None:
    resolver, _knowledge = _runtime()
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    result = SemanticRequestConsistencyValidator(resolver).validate(
        plan,
        raw_request="Explain DNS",
        resolved_target=None,
    )

    assert result.status is SemanticPlanValidationStatus.VALID
    assert result.reason is SemanticPlanValidationReason.VALID


def test_direct_answer_does_not_treat_chat_text_as_target() -> None:
    resolver, _knowledge = _runtime()
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    result = SemanticRequestConsistencyValidator(resolver).validate(
        plan,
        raw_request="hello",
        resolved_target=None,
    )

    assert result.status is SemanticPlanValidationStatus.VALID


def test_source_phrase_is_not_reinterpreted_as_target() -> None:
    resolver, _knowledge = _runtime()
    plan = _environment_plan(
        target="localhost",
        source=SourceConstraint.GRAFANA,
    )

    result = SemanticRequestConsistencyValidator(resolver).validate(
        plan,
        raw_request="check cpu from Grafana only",
        resolved_target="localhost",
    )

    assert result.status is SemanticPlanValidationStatus.VALID


@pytest.mark.parametrize(
    ("plan", "field"),
    (
        (
            SemanticPlan(
                route=SemanticPlanRoute.DIRECT_ANSWER,
                domain=RequestDomain.GENERAL,
                execution_intent=ExecutionIntent.EXPLAIN,
                source_constraints=(SourceConstraint.URL_ONLY,),
                freshness=FreshnessRequirement.STABLE,
                explicit_url="https://docs.example.com/page",
                deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
                clarification=ClarificationState.NOT_REQUIRED,
            ),
            "request.route",
        ),
        (
            SemanticPlan(
                route=SemanticPlanRoute.CAPABILITY_ASSISTED,
                domain=RequestDomain.GENERAL,
                execution_intent=ExecutionIntent.EXPLAIN,
                source_constraints=(SourceConstraint.URL_ONLY,),
                freshness=FreshnessRequirement.STABLE,
                explicit_url="https://docs.example.com/page",
                deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
                clarification=ClarificationState.NOT_REQUIRED,
            ),
            "request.domain",
        ),
    ),
)
def test_harness_rejects_explicit_url_plan_that_bypasses_external_fetch(
    plan: SemanticPlan,
    field: str,
) -> None:
    resolver, knowledge = _runtime()

    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        plan,
        raw_request="Read https://docs.example.com/page and report its value.",
    )

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.REQUEST_CONFLICT
    assert result.validation.values[0].field == field
    assert result.sources is None


def test_harness_allows_url_literal_content_generation_without_fetch() -> None:
    resolver, knowledge = _runtime()
    plan = SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.CONTENT_GENERATION,
        execution_intent=ExecutionIntent.GENERATE_CONTENT,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    result = SemanticPlanHarnessValidator(resolver, knowledge).validate(
        plan,
        raw_request=(
            "Write a config referencing https://example.com/app.tar.gz, "
            "but do not fetch it."
        ),
    )

    assert result.validation.status is SemanticPlanValidationStatus.VALID
