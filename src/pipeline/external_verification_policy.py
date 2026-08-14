"""Pure policy for deterministic external-verification routing.

The policy is deliberately ignorant of providers, credentials, and network
state.  It says whether a request *requires* external evidence; a later
planner decides whether that evidence can be collected under the configured
budget and source constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from src.pipeline.request_frame import RequestFrame
from src.pipeline.request_semantics import (
    ExternalNeed,
    RequestDomain,
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


class ExternalVerificationDecision(Enum):
    NONE = auto()
    REQUIRED = auto()
    EXPLICIT = auto()
    URL = auto()


@dataclass(frozen=True, slots=True)
class ExternalVerificationPolicyResult:
    decision: ExternalVerificationDecision
    reason: str
    blocked_by_source_constraint: bool = False

    @property
    def requires_verification(self) -> bool:
        return self.decision is not ExternalVerificationDecision.NONE


@dataclass(frozen=True, slots=True)
class SemanticFreshnessValidationResult:
    """Normalized freshness invariant for the semantic-plan harness."""

    validation: SemanticPlanValidationResult
    requires_live_evidence: bool = False
    evidence_family: str | None = None


class ExternalVerificationPolicy:
    """Map RequestFrame semantics to a provider-independent decision."""

    def decide(self, frame: RequestFrame) -> ExternalVerificationPolicyResult:
        if frame.external_need is ExternalNeed.NONE:
            return ExternalVerificationPolicyResult(
                ExternalVerificationDecision.NONE,
                "stable knowledge or live-environment request",
            )

        if SourceConstraint.NO_INTERNET in frame.source_constraints or SourceConstraint.INTERNET in frame.excluded_sources:
            return ExternalVerificationPolicyResult(
                self._decision(frame.external_need),
                "external verification conflicts with the no-Internet source constraint",
                blocked_by_source_constraint=True,
            )

        if frame.url_error:
            return ExternalVerificationPolicyResult(
                ExternalVerificationDecision.URL,
                frame.url_error,
            )

        return ExternalVerificationPolicyResult(
            self._decision(frame.external_need),
            {
                ExternalNeed.REQUIRED: "currentness requires external evidence",
                ExternalNeed.EXPLICIT: "user explicitly requested external verification",
                ExternalNeed.URL: "user supplied an explicit URL",
            }[frame.external_need],
        )

    def validate_semantic_plan(
        self,
        plan: SemanticPlan,
        *,
        verification_available: bool,
    ) -> SemanticFreshnessValidationResult:
        """Validate normalized freshness without inspecting raw request text."""

        if not isinstance(plan, SemanticPlan):
            raise TypeError("plan must be a SemanticPlan.")
        if plan.freshness in {
            FreshnessRequirement.UNSPECIFIED,
            FreshnessRequirement.UNKNOWN,
        }:
            return SemanticFreshnessValidationResult(
                SemanticPlanValidationResult.clarify(
                    plan,
                    SemanticPlanValidationReason.PLANNER_UNCERTAIN,
                )
            )

        requires_live = plan.freshness in {
            FreshnessRequirement.CURRENT,
            FreshnessRequirement.LATEST,
            FreshnessRequirement.RECENT,
            FreshnessRequirement.REAL_TIME,
        }
        if not requires_live:
            return SemanticFreshnessValidationResult(
                SemanticPlanValidationResult.valid(plan)
            )

        family = (
            "external"
            if plan.domain is RequestDomain.EXTERNAL_INFORMATION
            else "environment"
        )
        trace_value = SemanticPlanValidationValue.safe(
            "freshness.requirement",
            original=plan.freshness.value,
            normalized=f"live_{family}_evidence",
        )
        if plan.route is SemanticPlanRoute.DIRECT_ANSWER:
            return SemanticFreshnessValidationResult(
                SemanticPlanValidationResult.reject(
                    SemanticPlanValidationReason.FRESHNESS_UNVERIFIED,
                    plan=plan,
                    values=(trace_value,),
                ),
                requires_live_evidence=True,
                evidence_family=family,
            )

        if family == "external":
            internet_blocked = (
                SourceConstraint.NO_INTERNET in plan.source_constraints
                or SourceConstraint.INTERNET in plan.excluded_sources
                or SourceConstraint.URL_ONLY in plan.excluded_sources
            )
            if internet_blocked or not verification_available:
                return SemanticFreshnessValidationResult(
                    SemanticPlanValidationResult.unavailable(
                        plan,
                        SemanticPlanValidationReason.FRESHNESS_UNAVAILABLE,
                        values=(trace_value,),
                    ),
                    requires_live_evidence=True,
                    evidence_family=family,
                )

        return SemanticFreshnessValidationResult(
            SemanticPlanValidationResult.valid(plan, values=(trace_value,)),
            requires_live_evidence=True,
            evidence_family=family,
        )

    @staticmethod
    def _decision(need: ExternalNeed) -> ExternalVerificationDecision:
        return {
            ExternalNeed.REQUIRED: ExternalVerificationDecision.REQUIRED,
            ExternalNeed.EXPLICIT: ExternalVerificationDecision.EXPLICIT,
            ExternalNeed.URL: ExternalVerificationDecision.URL,
        }[need]
