"""Cross-check planner semantics against deterministic user constraints."""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.normalizer import Normalizer
from src.pipeline.request_semantics import (
    ExecutionIntent,
    InformationScope,
    RequestDomain,
    RequestSemantics,
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
_LIVE_EVIDENCE_FRESHNESS = frozenset(
    {
        FreshnessRequirement.CURRENT,
        FreshnessRequirement.LATEST,
        FreshnessRequirement.RECENT,
        FreshnessRequirement.REAL_TIME,
        FreshnessRequirement.HISTORICAL,
    }
)
_LIVE_ENVIRONMENT_ACTIONS = (
    "check ",
    "kiểm tra",
    "show ",
    "xem ",
    "list ",
    "trạng thái",
    "usage",
    "health",
)
_LIVE_ENVIRONMENT_CONCEPTS = (
    "cpu",
    "ram",
    "memory",
    "disk",
    "network",
    "load",
    "uptime",
    "service",
    "process",
    "container",
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

        # Derive raw-request constraints before trusting any route, domain, or
        # freshness proposed by the planner. In particular, a direct/general
        # plan must not suppress an explicit target or downgrade a request
        # that needs live environment evidence.
        semantics = RequestSemanticsClassifier().classify(raw_request)

        target_conflict = self._validate_target(
            plan,
            raw_request=raw_request,
            resolved_target=resolved_target,
        )
        if target_conflict is not None:
            return target_conflict

        explicit_url_conflict = _validate_explicit_url_fetch(plan, semantics)
        if explicit_url_conflict is not None:
            return explicit_url_conflict

        live_conflict = _validate_live_environment(
            plan,
            semantics,
            raw_request=raw_request,
        )
        if live_conflict is not None:
            return live_conflict

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

    def validate_multi_intent(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
        child_plans: tuple[SemanticPlan, ...],
        resolved_targets: tuple[str | None, ...],
    ) -> SemanticPlanValidationResult:
        """Keep parent request constraints authoritative across subplans.

        Subplan request text is model-produced decomposition context.  It can
        narrow a child operation, but it cannot erase an explicit parent
        target, source boundary, currentness requirement, or URL fetch
        requirement.  Direct-answer children need not carry evidence
        constraints themselves; at least one compatible evidence child must.
        """
        if plan.route is not SemanticPlanRoute.MULTI_INTENT:
            raise ValueError("plan must have the multi_intent route.")
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("raw_request must be non-empty text.")
        if len(child_plans) != len(resolved_targets) or any(
            not isinstance(child, SemanticPlan) for child in child_plans
        ):
            raise TypeError("child plans and resolved targets must align.")

        semantics = RequestSemanticsClassifier().classify(raw_request)
        requested_target, target_validation = self._explicit_request_target(
            plan,
            raw_request,
        )
        if target_validation is not None:
            return target_validation

        evidence_children = tuple(
            (child, target)
            for child, target in zip(child_plans, resolved_targets, strict=True)
            if child.route is SemanticPlanRoute.CAPABILITY_ASSISTED
        )
        environment_children = tuple(
            (child, target)
            for child, target in evidence_children
            if child.domain is RequestDomain.ENVIRONMENT
        )
        external_children = tuple(
            child
            for child, _target in evidence_children
            if child.domain is RequestDomain.EXTERNAL_INFORMATION
        )

        if requested_target is not None:
            actual_targets = tuple(target for _child, target in environment_children)
            if not actual_targets or any(
                target != requested_target for target in actual_targets
            ):
                return _conflict(
                    plan,
                    "request.target",
                    requested_target,
                    _target_names(actual_targets),
                )

        if semantics.explicit_url is not None and not any(
            child.explicit_url == semantics.explicit_url for child in external_children
        ):
            return _conflict(
                plan,
                "request.url",
                semantics.explicit_url,
                None,
            )

        requested_sources = _concrete_sources(semantics.source_constraints)
        if requested_sources and (
            not evidence_children
            or any(
                _concrete_sources(child.source_constraints) != requested_sources
                for child, _target in evidence_children
            )
        ):
            return _conflict(
                plan,
                "request.source",
                _source_names(requested_sources),
                _source_names(
                    _concrete_sources(evidence_children[0][0].source_constraints)
                    if len(evidence_children) == 1
                    else frozenset()
                ),
            )

        requested_exclusions = _concrete_sources(semantics.excluded_sources)
        if requested_exclusions and (
            not evidence_children
            or any(
                not requested_exclusions.issubset(
                    _concrete_sources(child.excluded_sources)
                )
                for child, _target in evidence_children
            )
        ):
            return _conflict(
                plan,
                "request.source_exclusion",
                _source_names(requested_exclusions),
                None,
            )

        if semantics.information_scope is InformationScope.CURRENT_EXTERNAL and not any(
            child.freshness in _CURRENT_FRESHNESS for child in external_children
        ):
            return _conflict(
                plan,
                "request.freshness",
                semantics.freshness_phrase or "current",
                None,
            )

        if _raw_request_requires_live_environment(semantics, raw_request) and not any(
            child.freshness in _LIVE_EVIDENCE_FRESHNESS
            for child, _target in environment_children
        ):
            return _conflict(
                plan,
                "request.freshness",
                "live_evidence",
                None,
            )

        return SemanticPlanValidationResult.valid(plan)

    def _validate_target(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
        resolved_target: str | None,
    ) -> SemanticPlanValidationResult | None:
        requested_target, target_validation = self._explicit_request_target(
            plan,
            raw_request,
        )
        if target_validation is not None:
            return target_validation

        if requested_target is None:
            return None
        if (
            plan.route is not SemanticPlanRoute.CAPABILITY_ASSISTED
            or plan.domain is not RequestDomain.ENVIRONMENT
        ):
            return _conflict(
                plan,
                "request.target",
                requested_target,
                None,
            )
        if resolved_target != requested_target:
            return _conflict(
                plan,
                "request.target",
                requested_target,
                resolved_target,
            )
        return None

    def _explicit_request_target(
        self,
        plan: SemanticPlan,
        raw_request: str,
    ) -> tuple[str | None, SemanticPlanValidationResult | None]:
        # A bare conversational word must not be misclassified as a hostname.
        # The normalizer identifies explicit request target syntax before the
        # resolver applies its deliberate bare-host compatibility fallback.
        if Normalizer().normalize(raw_request).target_raw is None:
            return None, None
        try:
            return (
                self.target_resolver.resolve_explicit_request_target(raw_request),
                None,
            )
        except AmbiguousTargetError:
            return (
                None,
                SemanticPlanValidationResult.clarify(
                    plan,
                    SemanticPlanValidationReason.TARGET_AMBIGUOUS,
                ),
            )
        except UnknownTargetError:
            return (
                None,
                SemanticPlanValidationResult.clarify(
                    plan,
                    SemanticPlanValidationReason.TARGET_UNKNOWN,
                ),
            )


def _concrete_sources(
    sources: tuple[SourceConstraint, ...],
) -> frozenset[SourceConstraint]:
    return frozenset(
        source for source in sources if source not in _NON_CONCRETE_SOURCES
    )


def _source_names(sources: frozenset[SourceConstraint]) -> str:
    return ",".join(sorted(source.name for source in sources))


def _target_names(targets: tuple[str | None, ...]) -> str | None:
    names = tuple(sorted({target for target in targets if target is not None}))
    return ",".join(names) if names else None


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


def _validate_live_environment(
    plan: SemanticPlan,
    semantics: RequestSemantics,
    *,
    raw_request: str,
) -> SemanticPlanValidationResult | None:
    """Keep raw live-environment requests on an evidence-bearing path."""
    if not _raw_request_requires_live_environment(semantics, raw_request):
        return None
    if plan.route is not SemanticPlanRoute.CAPABILITY_ASSISTED:
        return _conflict(
            plan,
            "request.route",
            SemanticPlanRoute.CAPABILITY_ASSISTED.value,
            plan.route.value,
        )
    if plan.domain is not RequestDomain.ENVIRONMENT:
        return _conflict(
            plan,
            "request.domain",
            RequestDomain.ENVIRONMENT.name,
            plan.domain.name,
        )
    if plan.freshness not in _LIVE_EVIDENCE_FRESHNESS:
        return _conflict(
            plan,
            "request.freshness",
            "live_evidence",
            plan.freshness.value,
        )
    return None


def _validate_explicit_url_fetch(
    plan: SemanticPlan,
    semantics: RequestSemantics,
) -> SemanticPlanValidationResult | None:
    """Keep fetch-authorizing URLs on the bounded external evidence path."""
    if semantics.explicit_url is None:
        return None
    if plan.route is not SemanticPlanRoute.CAPABILITY_ASSISTED:
        return _conflict(
            plan,
            "request.route",
            SemanticPlanRoute.CAPABILITY_ASSISTED.value,
            plan.route.value,
        )
    if plan.domain is not RequestDomain.EXTERNAL_INFORMATION:
        return _conflict(
            plan,
            "request.domain",
            RequestDomain.EXTERNAL_INFORMATION.name,
            plan.domain.name,
        )
    return None


def _raw_request_requires_live_environment(
    semantics: RequestSemantics,
    raw_request: str,
) -> bool:
    """Recognize only clear raw cues that require infrastructure evidence."""
    if semantics.execution_intent is ExecutionIntent.GENERATE_CONTENT:
        return False
    normalized = Normalizer().normalize(raw_request)
    if normalized.target_raw is not None:
        return True
    lower = raw_request.casefold()
    return any(marker in lower for marker in _LIVE_ENVIRONMENT_ACTIONS) and any(
        marker in lower for marker in _LIVE_ENVIRONMENT_CONCEPTS
    )


__all__ = ["SemanticRequestConsistencyValidator"]
