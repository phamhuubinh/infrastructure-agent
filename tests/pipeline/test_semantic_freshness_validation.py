from __future__ import annotations

from src.pipeline.external_verification_policy import ExternalVerificationPolicy
from src.pipeline.request_semantics import RequestDomain, SourceConstraint
from src.pipeline.semantic_plan import (
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
)
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationStatus,
)


def _plan(
    freshness: FreshnessRequirement,
    *,
    route: SemanticPlanRoute,
    domain: RequestDomain = RequestDomain.EXTERNAL_INFORMATION,
    sources: tuple[SourceConstraint, ...] = (SourceConstraint.INTERNET,),
) -> SemanticPlan:
    return SemanticPlan(
        route=route,
        domain=domain,
        source_constraints=sources,
        freshness=freshness,
    )


def test_current_direct_answer_is_rejected_without_model_memory_fallback() -> None:
    result = ExternalVerificationPolicy().validate_semantic_plan(
        _plan(FreshnessRequirement.CURRENT, route=SemanticPlanRoute.DIRECT_ANSWER),
        verification_available=True,
    )

    assert result.validation.status is SemanticPlanValidationStatus.REJECT
    assert result.validation.reason is SemanticPlanValidationReason.FRESHNESS_UNVERIFIED
    assert result.requires_live_evidence
    assert result.evidence_family == "external"


def test_normalized_vietnamese_and_english_freshness_share_one_invariant() -> None:
    policy = ExternalVerificationPolicy()
    # The planner wire has already normalized "hiện tại" and "current" to
    # the same enum; this validator never receives either raw phrase.
    vi = policy.validate_semantic_plan(
        _plan(
            FreshnessRequirement.CURRENT, route=SemanticPlanRoute.CAPABILITY_ASSISTED
        ),
        verification_available=True,
    )
    en = policy.validate_semantic_plan(
        _plan(
            FreshnessRequirement.CURRENT, route=SemanticPlanRoute.CAPABILITY_ASSISTED
        ),
        verification_available=True,
    )

    assert vi == en
    assert vi.validation.status is SemanticPlanValidationStatus.VALID


def test_unavailable_or_forbidden_external_verification_stays_explicit() -> None:
    policy = ExternalVerificationPolicy()
    unavailable = policy.validate_semantic_plan(
        _plan(FreshnessRequirement.LATEST, route=SemanticPlanRoute.CAPABILITY_ASSISTED),
        verification_available=False,
    )
    forbidden = policy.validate_semantic_plan(
        _plan(
            FreshnessRequirement.RECENT,
            route=SemanticPlanRoute.CAPABILITY_ASSISTED,
            sources=(SourceConstraint.NO_INTERNET,),
        ),
        verification_available=True,
    )

    assert unavailable.validation.status is SemanticPlanValidationStatus.UNAVAILABLE
    assert (
        forbidden.validation.reason
        is SemanticPlanValidationReason.FRESHNESS_UNAVAILABLE
    )


def test_live_environment_capability_and_stable_direct_answer_are_valid() -> None:
    policy = ExternalVerificationPolicy()
    live = policy.validate_semantic_plan(
        _plan(
            FreshnessRequirement.REAL_TIME,
            route=SemanticPlanRoute.CAPABILITY_ASSISTED,
            domain=RequestDomain.ENVIRONMENT,
            sources=(SourceConstraint.LINUX,),
        ),
        verification_available=False,
    )
    stable = policy.validate_semantic_plan(
        _plan(
            FreshnessRequirement.STABLE,
            route=SemanticPlanRoute.DIRECT_ANSWER,
            domain=RequestDomain.GENERAL,
            sources=(SourceConstraint.ANY,),
        ),
        verification_available=False,
    )

    assert live.validation.status is SemanticPlanValidationStatus.VALID
    assert live.evidence_family == "environment"
    assert stable.validation.status is SemanticPlanValidationStatus.VALID
    assert not stable.requires_live_evidence
