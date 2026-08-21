"""Deterministic pre-binding validation for model-proposed semantic plans."""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.basic_calculator import (
    CalculatorResultStatus,
    calculate_request,
)
from src.pipeline.external_verification_policy import (
    ExternalVerificationPolicy,
    SemanticFreshnessValidationResult,
)
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_mutation_validator import (
    SemanticMutationValidationResult,
    SemanticMutationValidator,
)
from src.pipeline.semantic_plan import (
    MAX_SEMANTIC_SUBPLANS,
    MAX_SUBPLAN_DEPENDENCIES,
    MAX_SUBPLAN_REQUEST_LENGTH,
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
    SemanticSubplan,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
    SemanticPlanValidationStatus,
    SemanticPlanValidationValue,
)
from src.pipeline.semantic_request_consistency import (
    SemanticRequestConsistencyValidator,
)
from src.pipeline.source_constraints import (
    SemanticSourceValidationResult,
    validate_semantic_sources,
)
from src.pipeline.target_resolver import (
    SemanticTargetValidationResult,
    TargetResolver,
)
from src.tool.knowledge_tool import KnowledgeTool


@dataclass(frozen=True, slots=True)
class SemanticPlanHarnessResult:
    validation: SemanticPlanValidationResult
    target: SemanticTargetValidationResult | None = None
    sources: SemanticSourceValidationResult | None = None
    freshness: SemanticFreshnessValidationResult | None = None
    mutation: SemanticMutationValidationResult | None = None
    subplans: tuple[SemanticPlanHarnessResult, ...] = ()

    @property
    def resolved_target(self) -> str | None:
        return self.target.resolved_target if self.target is not None else None

    @property
    def allowed_sources(self) -> frozenset[str] | None:
        return self.sources.allowed_sources if self.sources is not None else None

    def to_trace_dict(self) -> dict[str, object]:
        trace = self.validation.to_trace_dict()
        trace["resolved_target"] = self.resolved_target
        trace["allowed_sources"] = (
            sorted(self.allowed_sources) if self.allowed_sources is not None else None
        )
        trace["requires_live_evidence"] = bool(
            self.freshness and self.freshness.requires_live_evidence
        )
        trace["subplans"] = [item.to_trace_dict() for item in self.subplans]
        return trace


class SemanticPlanHarnessValidator:
    """Apply mutation, target, source and freshness gates before binding."""

    def __init__(
        self,
        target_resolver: TargetResolver,
        knowledge_tool: KnowledgeTool,
    ) -> None:
        if not isinstance(target_resolver, TargetResolver):
            raise TypeError("target_resolver must be a TargetResolver.")
        if not isinstance(knowledge_tool, KnowledgeTool):
            raise TypeError("knowledge_tool must be a KnowledgeTool.")
        self._target_resolver = target_resolver
        self._knowledge_tool = knowledge_tool

    def validate(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
        verification_available: bool = True,
        allow_implicit_localhost: bool = True,
    ) -> SemanticPlanHarnessResult:
        if plan.route is SemanticPlanRoute.MULTI_INTENT:
            return self._validate_multi_intent(
                plan,
                raw_request=raw_request,
                verification_available=verification_available,
            )

        mutation = SemanticMutationValidator().validate(plan, raw_request)
        if not _valid(mutation.validation):
            return SemanticPlanHarnessResult(
                validation=mutation.validation,
                mutation=mutation,
            )

        compute_validation = _validate_compute(plan)
        if not _valid(compute_validation):
            return SemanticPlanHarnessResult(validation=compute_validation)

        if (
            plan.route is SemanticPlanRoute.DIRECT_ANSWER
            and plan.target.kind is TargetReferenceKind.UNSPECIFIED
        ):
            target = SemanticTargetValidationResult(
                SemanticPlanValidationResult.valid(plan)
            )
        else:
            target = self._target_resolver.validate_semantic_target(
                plan,
                allow_implicit_localhost=allow_implicit_localhost,
            )
        if not _valid(target.validation):
            return SemanticPlanHarnessResult(
                validation=target.validation,
                target=target,
                mutation=mutation,
            )

        consistency = SemanticRequestConsistencyValidator(
            self._target_resolver
        ).validate(
            plan,
            raw_request=raw_request,
            resolved_target=target.resolved_target,
        )
        if not _valid(consistency):
            return SemanticPlanHarnessResult(
                validation=consistency,
                target=target,
                mutation=mutation,
            )

        sources = validate_semantic_sources(
            self._knowledge_tool,
            plan,
            target=target.resolved_target,
        )
        if not _valid(sources.validation):
            return SemanticPlanHarnessResult(
                validation=sources.validation,
                target=target,
                sources=sources,
                mutation=mutation,
            )

        freshness = ExternalVerificationPolicy().validate_semantic_plan(
            plan,
            verification_available=verification_available,
        )
        if not _valid(freshness.validation):
            return SemanticPlanHarnessResult(
                validation=freshness.validation,
                target=target,
                sources=sources,
                freshness=freshness,
                mutation=mutation,
            )

        values = _merge_values(
            target.validation.values,
            sources.validation.values,
            freshness.validation.values,
            consistency.values,
            mutation.validation.values,
        )
        return SemanticPlanHarnessResult(
            validation=SemanticPlanValidationResult.valid(plan, values=values),
            target=target,
            sources=sources,
            freshness=freshness,
            mutation=mutation,
        )

    def _validate_multi_intent(
        self,
        plan: SemanticPlan,
        *,
        raw_request: str,
        verification_available: bool,
    ) -> SemanticPlanHarnessResult:
        structural = _validate_multi_intent_structure(plan)
        if structural is not None:
            return SemanticPlanHarnessResult(validation=structural)

        # The parent request is the authority for the read-only boundary. A
        # child request is planner-authored decomposition text and must never
        # be able to turn an action request into a harmless-looking child.
        mutation = SemanticMutationValidator().validate(plan, raw_request)
        if not _valid(mutation.validation):
            return SemanticPlanHarnessResult(
                validation=mutation.validation,
                mutation=mutation,
            )

        validated: list[SemanticPlanHarnessResult] = []
        for item in plan.subplans:
            child = self.validate(
                item.plan,
                raw_request=item.request,
                verification_available=verification_available,
                allow_implicit_localhost=False,
            )
            validated.append(child)
            if not _valid(child.validation):
                return SemanticPlanHarnessResult(
                    validation=_parent_subplan_failure(plan, child.validation),
                    subplans=tuple(validated),
                    mutation=mutation,
                )

        consistency = SemanticRequestConsistencyValidator(
            self._target_resolver
        ).validate_multi_intent(
            plan,
            raw_request=raw_request,
            child_plans=tuple(item.plan for item in plan.subplans),
            resolved_targets=tuple(child.resolved_target for child in validated),
        )
        if not _valid(consistency):
            return SemanticPlanHarnessResult(
                validation=consistency,
                subplans=tuple(validated),
                mutation=mutation,
            )
        return SemanticPlanHarnessResult(
            validation=SemanticPlanValidationResult.valid(plan),
            subplans=tuple(validated),
            mutation=mutation,
        )


def _validate_multi_intent_structure(
    plan: SemanticPlan,
) -> SemanticPlanValidationResult | None:
    if not isinstance(plan.subplans, tuple) or any(
        not isinstance(item, SemanticSubplan) for item in plan.subplans
    ):
        return SemanticPlanValidationResult.reject(
            SemanticPlanValidationReason.MALFORMED_PLAN,
            plan=plan,
        )
    if len(plan.subplans) < 2 or len(plan.subplans) > MAX_SEMANTIC_SUBPLANS:
        return SemanticPlanValidationResult.reject(
            SemanticPlanValidationReason.MALFORMED_PLAN,
            plan=plan,
        )
    for index, item in enumerate(plan.subplans):
        if (
            not isinstance(item.request, str)
            or not item.request
            or item.request != item.request.strip()
            or len(item.request) > MAX_SUBPLAN_REQUEST_LENGTH
            or any(ord(character) < 32 for character in item.request)
        ):
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.MALFORMED_PLAN,
                plan=plan,
            )
        if (
            not isinstance(item.plan, SemanticPlan)
            or item.plan.route
            not in {
                SemanticPlanRoute.DIRECT_ANSWER,
                SemanticPlanRoute.CAPABILITY_ASSISTED,
            }
            or item.plan.subplans
        ):
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.MALFORMED_PLAN,
                plan=plan,
            )
        if (
            not isinstance(item.depends_on, tuple)
            or len(item.depends_on) > MAX_SUBPLAN_DEPENDENCIES
            or len(set(item.depends_on)) != len(item.depends_on)
            or any(
                type(dep) is not int or dep < 0 or dep >= index
                for dep in item.depends_on
            )
        ):
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.MALFORMED_PLAN,
                plan=plan,
            )
        if SourceConstraint.UNSPECIFIED in item.plan.source_constraints:
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.MALFORMED_PLAN,
                plan=plan,
            )
        if item.plan.freshness in {
            FreshnessRequirement.UNSPECIFIED,
            FreshnessRequirement.UNKNOWN,
        }:
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.MALFORMED_PLAN,
                plan=plan,
            )
        if (
            item.plan.route is SemanticPlanRoute.CAPABILITY_ASSISTED
            and item.plan.domain is RequestDomain.ENVIRONMENT
            and item.plan.target.kind
            not in {TargetReferenceKind.EXPLICIT, TargetReferenceKind.INHERITED}
        ):
            return SemanticPlanValidationResult.clarify(
                plan,
                SemanticPlanValidationReason.TARGET_MISSING,
            )
    return None


def _parent_subplan_failure(
    plan: SemanticPlan,
    child: SemanticPlanValidationResult,
) -> SemanticPlanValidationResult:
    if child.status is SemanticPlanValidationStatus.CLARIFY:
        return SemanticPlanValidationResult.clarify(plan, child.reason)
    if child.status is SemanticPlanValidationStatus.UNAVAILABLE:
        return SemanticPlanValidationResult.unavailable(plan, child.reason)
    return SemanticPlanValidationResult.reject(child.reason, plan=plan)


def _validate_compute(plan: SemanticPlan) -> SemanticPlanValidationResult:
    if plan.deterministic_compute is DeterministicComputeIntent.REQUIRED:
        if plan.calculation is None:
            return SemanticPlanValidationResult.clarify(
                plan,
                SemanticPlanValidationReason.COMPUTE_MISSING,
            )
        if plan.route is not SemanticPlanRoute.DIRECT_ANSWER:
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.COMPUTE_CONFLICT,
                plan=plan,
            )
        result = calculate_request(plan.calculation)
        if result.status is CalculatorResultStatus.AMBIGUOUS:
            return SemanticPlanValidationResult.clarify(
                plan,
                SemanticPlanValidationReason.COMPUTE_INVALID,
            )
        if not result.ok:
            return SemanticPlanValidationResult.reject(
                SemanticPlanValidationReason.COMPUTE_INVALID,
                plan=plan,
            )
        return SemanticPlanValidationResult.valid(plan)
    if plan.calculation is not None:
        return SemanticPlanValidationResult.reject(
            SemanticPlanValidationReason.COMPUTE_CONFLICT,
            plan=plan,
        )
    return SemanticPlanValidationResult.valid(plan)


_PLANNER_ANSWER_DOMAINS = frozenset(
    {RequestDomain.GENERAL, RequestDomain.CONTENT_GENERATION}
)
_PLANNER_ANSWER_INTENTS = frozenset(
    {ExecutionIntent.EXPLAIN, ExecutionIntent.GENERATE_CONTENT}
)
_PLANNER_ANSWER_FRESHNESS = frozenset(
    {FreshnessRequirement.STABLE, FreshnessRequirement.HISTORICAL}
)
_PLANNER_ANSWER_SOURCES = frozenset(
    {SourceConstraint.ANY, SourceConstraint.NO_INTERNET}
)


def planner_final_answer_allowed(plan: SemanticPlan) -> bool:
    """Whether a validated plan may deliver a planner-provided final answer.

    This is the deterministic eligibility gate for the single-call path.
    It is a conservative allow-list: only trivial, stable, tool-free
    requests may use planner answer prose.  Requests that need live
    infrastructure, current/external information, mutation, deterministic
    calculation, capability execution, or clarification always take their
    existing validated paths and never consume planner final text.
    """

    return (
        not plan.subplans
        and plan.route is SemanticPlanRoute.DIRECT_ANSWER
        and plan.domain in _PLANNER_ANSWER_DOMAINS
        and plan.execution_intent in _PLANNER_ANSWER_INTENTS
        and plan.freshness in _PLANNER_ANSWER_FRESHNESS
        and plan.deterministic_compute is DeterministicComputeIntent.NOT_REQUIRED
        and plan.calculation is None
        and plan.clarification is ClarificationState.NOT_REQUIRED
        and plan.target.kind is TargetReferenceKind.UNSPECIFIED
        and plan.explicit_url is None
        and all(item in _PLANNER_ANSWER_SOURCES for item in plan.source_constraints)
    )


def _valid(result: SemanticPlanValidationResult) -> bool:
    return result.status is SemanticPlanValidationStatus.VALID


def _merge_values(
    *groups: tuple[SemanticPlanValidationValue, ...],
) -> tuple[SemanticPlanValidationValue, ...]:
    merged: dict[str, SemanticPlanValidationValue] = {}
    for group in groups:
        for value in group:
            merged[value.field] = value
    return tuple(merged.values())


__all__ = [
    "SemanticPlanHarnessResult",
    "SemanticPlanHarnessValidator",
    "planner_final_answer_allowed",
]
