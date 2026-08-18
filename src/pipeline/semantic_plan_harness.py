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
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
    SemanticPlanValidationStatus,
    SemanticPlanValidationValue,
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
            mutation.validation.values,
        )
        return SemanticPlanHarnessResult(
            validation=SemanticPlanValidationResult.valid(plan, values=values),
            target=target,
            sources=sources,
            freshness=freshness,
            mutation=mutation,
        )


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
        plan.route is SemanticPlanRoute.DIRECT_ANSWER
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
