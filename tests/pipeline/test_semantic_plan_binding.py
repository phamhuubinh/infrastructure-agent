from __future__ import annotations

from dataclasses import replace

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
from src.pipeline.semantic_plan_binding import SemanticPlanBinder
from src.pipeline.semantic_plan_harness import SemanticPlanHarnessValidator
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationStatus,
)
from src.pipeline.target_resolver import TargetResolver
from src.pipeline.time_range_resolver import TimeRange
from src.tool.grafana_tool import GrafanaTool
from src.tool.internet_tool import InternetTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


def _environment_plan(
    concept: str,
    *,
    service: str | None = None,
    source: SourceConstraint = SourceConstraint.ANY,
) -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.ENVIRONMENT,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        target=TargetReference(TargetReferenceKind.EXPLICIT, "localhost"),
        source_constraints=(source,),
        freshness=FreshnessRequirement.CURRENT,
        concept=concept,
        service=service,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _runtime(
    *,
    internet: bool = False,
    grafana: bool = False,
) -> tuple[KnowledgeTool, TargetResolver]:
    registry = TargetRegistry()
    registry.add("localhost")
    if internet:
        registry.register_tool("internet", InternetTool())
    if grafana:
        registry.register_tool("grafana", GrafanaTool("http://grafana", "token"))
    return KnowledgeTool(registry), TargetResolver(registry)


def _bind(
    plan: SemanticPlan,
    raw_request: str,
    *,
    internet: bool = False,
    grafana: bool = False,
    timeframe: TimeRange | None = None,
):
    tool, resolver = _runtime(internet=internet, grafana=grafana)
    harness = SemanticPlanHarnessValidator(resolver, tool).validate(
        plan,
        raw_request=raw_request,
        verification_available=True,
    )
    return SemanticPlanBinder(tool).bind(
        harness,
        raw_request=raw_request,
        timeframe=timeframe,
    )


@pytest.mark.parametrize(
    ("concept", "expected_capability", "expected_resource"),
    (
        ("cpu", "CPU Information", "get_cpu"),
        ("memory", "Memory Information", "get_memory"),
        ("service", "Service Status", "get_service"),
    ),
)
def test_environment_plans_bind_existing_capability_contracts(
    concept: str,
    expected_capability: str,
    expected_resource: str,
) -> None:
    plan = _environment_plan(
        concept,
        service="nginx" if concept == "service" else None,
    )

    result = _bind(plan, f"check {concept}")

    assert result.bound
    assert result.capabilities[0].reference.name == expected_capability
    assert result.capabilities[0].resource == expected_resource
    assert result.capabilities[0].source == "localhost"
    if concept == "service":
        assert result.capabilities[0].arguments["name"] == "nginx"


def test_current_web_plan_binds_search_metadata_and_preserves_freshness() -> None:
    plan = SemanticPlan(
        route=SemanticPlanRoute.CAPABILITY_ASSISTED,
        domain=RequestDomain.EXTERNAL_INFORMATION,
        execution_intent=ExecutionIntent.INSPECT_READ_ONLY,
        source_constraints=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.LATEST,
        concept="current version",
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )

    result = _bind(plan, "latest Python version", internet=True)

    assert result.bound
    assert result.freshness is FreshnessRequirement.LATEST
    assert result.capabilities[0].reference.name == "Internet Resource Access"
    assert result.capabilities[0].resource == "web_search"
    assert result.capabilities[0].arguments["query"] == "latest Python version"


def test_missing_service_parameter_is_structured_and_never_dispatched() -> None:
    result = _bind(_environment_plan("service"), "check service")

    assert result.validation.status is SemanticPlanValidationStatus.CLARIFY
    assert result.validation.reason is SemanticPlanValidationReason.PARAMETER_MISSING
    assert result.capabilities == ()


def test_source_only_plan_cannot_substitute_an_unavailable_capability() -> None:
    result = _bind(
        _environment_plan("cpu", source=SourceConstraint.GRAFANA),
        "check cpu from Grafana only",
        grafana=True,
    )

    assert result.validation.status is SemanticPlanValidationStatus.UNAVAILABLE
    assert (
        result.validation.reason is SemanticPlanValidationReason.CAPABILITY_UNAVAILABLE
    )
    assert result.capabilities == ()


def test_binding_preserves_the_validated_timeframe() -> None:
    timeframe = TimeRange(
        start=100,
        end=200,
        granularity="1m",
        timezone="UTC",
        source_phrase="last 100 seconds",
    )

    result = _bind(
        _environment_plan("cpu"),
        "check cpu for the last 100 seconds",
        timeframe=timeframe,
    )

    assert result.bound
    assert result.timeframe is timeframe
    assert result.request is not None
    assert result.request.request_frame is not None
    assert result.request.request_frame.timeframe is timeframe


def test_invalid_harness_result_cannot_bind() -> None:
    tool, resolver = _runtime()
    invalid_plan = replace(
        _environment_plan("cpu"),
        target=TargetReference(TargetReferenceKind.EXPLICIT, "doesnotexist123"),
    )
    harness = SemanticPlanHarnessValidator(resolver, tool).validate(
        invalid_plan,
        raw_request="check cpu on doesnotexist123",
    )

    result = SemanticPlanBinder(tool).bind(
        harness,
        raw_request="check cpu on doesnotexist123",
    )

    assert not result.bound
    assert result.validation.reason is SemanticPlanValidationReason.TARGET_UNKNOWN
    assert result.capabilities == ()
