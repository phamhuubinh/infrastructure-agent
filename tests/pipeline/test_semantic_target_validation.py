from __future__ import annotations

from src.pipeline.alias_store import (
    AliasLifecycle,
    AliasRecord,
    AliasScope,
    AliasStore,
)
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    ClarificationState,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
    TargetReference,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationStatus,
)
from src.pipeline.target_resolver import TargetResolver
from src.tool.target_registry import TargetRegistry


def _plan(target: TargetReference, *, route=SemanticPlanRoute.CAPABILITY_ASSISTED):
    return SemanticPlan(
        route=route,
        domain=(
            RequestDomain.ENVIRONMENT
            if route is SemanticPlanRoute.CAPABILITY_ASSISTED
            else RequestDomain.GENERAL
        ),
        execution_intent=(
            ExecutionIntent.INSPECT_READ_ONLY
            if route is SemanticPlanRoute.CAPABILITY_ASSISTED
            else ExecutionIntent.EXPLAIN
        ),
        target=target,
        source_constraints=(SourceConstraint.ANY,),
        freshness=(
            FreshnessRequirement.CURRENT
            if route is SemanticPlanRoute.CAPABILITY_ASSISTED
            else FreshnessRequirement.STABLE
        ),
        clarification=ClarificationState.NOT_REQUIRED,
    )


def _resolver() -> TargetResolver:
    registry = TargetRegistry()
    registry.add("localhost")
    registry.add("server01")
    aliases = AliasStore(
        (
            AliasRecord(
                alias="primary",
                target="server01",
                scope=AliasScope.GLOBAL,
                lifecycle=AliasLifecycle.ACTIVE,
                reviewer="test",
                evidence_count=1,
            ),
        )
    )
    return TargetResolver(registry, alias_store=aliases)


def test_explicit_target_and_alias_resolve_auditably() -> None:
    resolver = _resolver()

    exact = resolver.validate_semantic_target(
        _plan(TargetReference(TargetReferenceKind.EXPLICIT, "server01"))
    )
    alias = resolver.validate_semantic_target(
        _plan(TargetReference(TargetReferenceKind.EXPLICIT, "primary"))
    )

    assert exact.validation.status is SemanticPlanValidationStatus.VALID
    assert exact.resolved_target == "server01"
    assert exact.candidates[0].source == "exact"
    assert alias.resolved_target == "server01"
    assert alias.candidates[0].source == "scoped_alias"
    assert alias.to_trace_dict()["resolved_target"] == "server01"


def test_explicit_unknown_never_becomes_localhost() -> None:
    resolver = _resolver()

    for name in ("testxyz999", "doesnotexist123"):
        result = resolver.validate_semantic_target(
            _plan(TargetReference(TargetReferenceKind.EXPLICIT, name))
        )
        assert result.validation.status is SemanticPlanValidationStatus.CLARIFY
        assert result.validation.reason is SemanticPlanValidationReason.TARGET_UNKNOWN
        assert result.resolved_target is None
        assert "localhost" not in str(result.to_trace_dict())


def test_ambiguous_and_inherited_references_remain_distinct() -> None:
    resolver = _resolver()
    ambiguous = resolver.validate_semantic_target(
        _plan(TargetReference(TargetReferenceKind.AMBIGUOUS, "server"))
    )
    inherited = resolver.validate_semantic_target(
        _plan(TargetReference(TargetReferenceKind.INHERITED, "server01"))
    )

    assert ambiguous.validation.reason is SemanticPlanValidationReason.TARGET_AMBIGUOUS
    assert inherited.validation.status is SemanticPlanValidationStatus.VALID
    assert inherited.resolved_target == "server01"


def test_localhost_default_applies_only_to_genuinely_omitted_environment_target() -> (
    None
):
    resolver = _resolver()
    omitted_environment = resolver.validate_semantic_target(_plan(TargetReference()))
    omitted_direct = resolver.validate_semantic_target(
        _plan(TargetReference(), route=SemanticPlanRoute.DIRECT_ANSWER)
    )

    assert omitted_environment.resolved_target == "localhost"
    assert omitted_environment.candidates[0].source == "implicit_default"
    assert omitted_direct.resolved_target is None
    assert omitted_direct.validation.status is SemanticPlanValidationStatus.VALID
