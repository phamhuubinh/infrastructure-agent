"""Cross-check planner semantics against deterministic user constraints."""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.request_semantics import (
    InformationScope,
    RequestDomain,
    RequestSemanticsClassifier,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
)
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
    SemanticPlanValidationValue,
)
from src.pipeline.target_resolver import (
    AmbiguousTargetError,
    TargetResolver,
    UnknownTargetError,
)

_NON_CONCRETE_SOURCES = frozenset(
    {
        SourceConstraint.ANY,
        SourceConstraint.UNSPECIFIED,
        SourceConstraint.UNKNOWN,
    }
)
_CURRENT_FRESHNESS = frozenset(
    {
        FreshnessRequirement.CURRENT,
        FreshnessRequirement.LATEST,
        FreshnessRequirement.RECENT,
        FreshnessRequirement.REAL_TIME,
    }
)


@dataclass(frozen=True, slots=True)
class SemanticRequestConsistencyValidator:
    """Reject a planner plan that weakens hard constraints in raw user text."""

    target_resolver: TargetResolver

    def __post_init__(self) -> None:
        if not isinstance(self.target_resolver, TargetResolver):
            raise TypeError("target_resolver must be a TargetResolver.")

    def validate(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
        resolved_target: str | None,
    ) -> SemanticPlanValidationResult:
        if not isinstance(plan, SemanticPlan):
            raise TypeError("plan must be a SemanticPlan.")
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("raw_request must be non-empty text.")

        target_conflict = self._validate_target(
            plan,
            raw_request=raw_request,
            resolved_target=resolved_target,
        )
        if target_conflict is not None:
            return target_conflict

        semantics = RequestSemanticsClassifier().classify(raw_request)

        requested_sources = _concrete_sources(semantics.source_constraints)
        planned_sources = _concrete_sources(plan.source_constraints)
        if requested_sources and planned_sources != requested_sources:
            return _conflict(
                plan,
                "request.source",
                _source_names(requested_sources),
                _source_names(planned_sources),
            )

        requested_exclusions = _concrete_sources(semantics.excluded_sources)
        planned_exclusions = _concrete_sources(plan.excluded_sources)
        if not requested_exclusions.issubset(planned_exclusions):
            return _conflict(
                plan,
                "request.source_exclusion",
                _source_names(requested_exclusions),
                _source_names(planned_exclusions),
            )

        if (
            semantics.explicit_url is not None
            and plan.explicit_url != semantics.explicit_url
        ):
            return _conflict(
                plan,
                "request.url",
                semantics.explicit_url,
                plan.explicit_url,
            )

        requires_current = (
            semantics.information_scope is InformationScope.CURRENT_EXTERNAL
            or (
                semantics.freshness_phrase is not None
                and semantics.information_scope is InformationScope.LIVE_ENVIRONMENT
            )
        )
        if requires_current and plan.freshness not in _CURRENT_FRESHNESS:
            return _conflict(
                plan,
                "request.freshness",
                semantics.freshness_phrase or "current",
                plan.freshness.value,
            )

        if (
            semantics.information_scope is InformationScope.CURRENT_EXTERNAL
            and plan.domain is not RequestDomain.EXTERNAL_INFORMATION
        ):
            return _conflict(
                plan,
                "request.domain",
                RequestDomain.EXTERNAL_INFORMATION.name,
                plan.domain.name,
            )

        return SemanticPlanValidationResult.valid(plan)

    def _validate_target(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
        resolved_target: str | None,
    ) -> SemanticPlanValidationResult | None:
        # Target consistency is an execution-boundary constraint. Direct
        # answers and external-verification plans do not dispatch to an
        # infrastructure target, so target-like words in those requests must
        # not be reinterpreted as hostnames.
        if (
            plan.route is not SemanticPlanRoute.CAPABILITY_ASSISTED
            or plan.domain is not RequestDomain.ENVIRONMENT
        ):
            return None

        try:
            requested_target = self.target_resolver.resolve_explicit_request_target(
                raw_request
            )
        except AmbiguousTargetError:
            return SemanticPlanValidationResult.clarify(
                plan,
                SemanticPlanValidationReason.TARGET_AMBIGUOUS,
            )
        except UnknownTargetError:
            return SemanticPlanValidationResult.clarify(
                plan,
                SemanticPlanValidationReason.TARGET_UNKNOWN,
            )

        if requested_target is None:
            return None
        if resolved_target != requested_target:
            return _conflict(
                plan,
                "request.target",
                requested_target,
                resolved_target,
            )
        return None


def _concrete_sources(
    sources: tuple[SourceConstraint, ...],
) -> frozenset[SourceConstraint]:
    return frozenset(source for source in sources if source not in _NON_CONCRETE_SOURCES)


def _source_names(sources: frozenset[SourceConstraint]) -> str:
    return ",".join(sorted(source.name for source in sources))


def _conflict(
    plan: SemanticPlan,
    field: str,
    requested: str | None,
    planned: str | None,
) -> SemanticPlanValidationResult:
    return SemanticPlanValidationResult.reject(
        SemanticPlanValidationReason.REQUEST_CONFLICT,
        plan=plan,
        values=(
            SemanticPlanValidationValue.safe(
                field,
                original=requested,
                normalized=planned,
            ),
        ),
    )


__all__ = ["SemanticRequestConsistencyValidator"]
