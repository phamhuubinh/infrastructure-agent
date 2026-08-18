"""Provider-neutral structured-output adapter for semantic planning.

This boundary can request a typed plan but has no execution, capability, or
tool interface.  Provider implementations receive only prompt text, the JSON
Schema, call metadata, and a bounded timeout.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from src.model.protocol.semantic_planner_prompt import (
    PlannerPromptContext,
    build_semantic_planner_prompt,
)
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    ClarificationState,
    SemanticPlan,
    SemanticPlanRoute,
    TargetReferenceKind,
)
from src.pipeline.semantic_plan_wire import (
    PlannerWireOutput,
    SemanticPlanWireError,
    planner_output_from_json,
    planner_output_from_wire,
)
from src.shared.execution.command_result import redact_sensitive

MAX_PLANNER_PROVIDERS = 8
MAX_PLANNER_ERROR_CHARS = 160


class ModelCallPurpose(str, Enum):
    """Purpose tag kept separate from assessment/final-response calls."""

    PLANNER = "planner"


@dataclass(frozen=True, slots=True)
class PlannerProviderRequest:
    """The complete authority-free request sent to one model provider."""

    purpose: ModelCallPurpose
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, object]
    timeout_seconds: float
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlannerProviderResponse:
    """Raw structured provider output before semantic-plan validation."""

    payload: object
    provider: str
    model: str
    raw_usage: Mapping[str, object] | None = None


@runtime_checkable
class StructuredPlannerProvider(Protocol):
    """Narrow model-provider protocol; deliberately exposes no tool methods."""

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        """Return one schema-constrained response or raise a provider error."""


class PlannerFailureReason(str, Enum):
    NO_PROVIDER = "no_provider"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    INVALID_OUTPUT = "invalid_output"


class SemanticPlannerOutcomeStatus(str, Enum):
    """Bounded outcome at the untrusted planner boundary."""

    VALID = "valid"
    CLARIFY = "clarify"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class SemanticPlannerOutcomeReason(str, Enum):
    """Stable, trace-safe reasons that never require message parsing."""

    PLAN_VALID = "plan_valid"
    CLARIFICATION_REQUIRED = "clarification_required"
    AMBIGUOUS_TARGET = "ambiguous_target"
    INCOMPLETE_PLAN = "incomplete_plan"
    CONTRADICTORY_PLAN = "contradictory_plan"
    PLANNER_UNCERTAIN = "planner_uncertain"
    NO_PROVIDER = "no_provider"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    MALFORMED_OUTPUT = "malformed_output"


@dataclass(frozen=True, slots=True)
class PlannerAttemptFailure:
    provider: str
    reason: PlannerFailureReason
    message: str


class SemanticPlannerError(RuntimeError):
    """All configured planner providers failed explicitly and safely."""

    def __init__(self, failures: tuple[PlannerAttemptFailure, ...]) -> None:
        self.failures = failures
        self.reason = (
            PlannerFailureReason.NO_PROVIDER if not failures else failures[-1].reason
        )
        if not failures:
            message = "No semantic-planner provider is configured."
        else:
            details = "; ".join(
                f"{item.provider}:{item.reason.value}:{item.message}"
                for item in failures
            )
            message = f"Semantic planning failed: {details}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SemanticPlannerResult:
    """Validated plan plus provider metadata kept outside the plan itself.

    ``final_answer`` is optional planner-provided answer prose kept outside
    ``plan``.  It is not trusted output: only the harness eligibility gate
    and the final-delivery validations may release it to the user.
    """

    plan: SemanticPlan
    provider: str
    model: str
    raw_usage: Mapping[str, object] | None
    purpose: ModelCallPurpose
    latency_ms: float
    final_answer: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticPlannerOutcome:
    """Fail-closed planner result suitable for orchestration and tracing.

    ``plan`` is deliberately absent for failures and unsupported semantics, so
    malformed planner output cannot accidentally reach capability dispatch.
    A clarification may retain the parsed advisory plan, but still is not a
    valid execution plan.
    """

    status: SemanticPlannerOutcomeStatus
    reason: SemanticPlannerOutcomeReason
    plan: SemanticPlan | None = None
    clarification_field: str | None = None
    result: SemanticPlannerResult | None = None
    failures: tuple[PlannerAttemptFailure, ...] = ()

    @property
    def can_dispatch(self) -> bool:
        return self.status is SemanticPlannerOutcomeStatus.VALID

    def to_trace_dict(self) -> dict[str, object]:
        trace: dict[str, object] = {
            "status": self.status.value,
            "reason": self.reason.value,
            "can_dispatch": self.can_dispatch,
        }
        if self.clarification_field is not None:
            trace["clarification_field"] = self.clarification_field
        if self.result is not None:
            trace["provider"] = self.result.provider
            trace["model"] = self.result.model
            trace["latency_ms"] = self.result.latency_ms
        if self.failures:
            trace["attempts"] = [
                {"provider": item.provider, "reason": item.reason.value}
                for item in self.failures
            ]
        return trace


class SemanticPlannerAdapter:
    """Try configured providers in order and validate their structured output."""

    def __init__(
        self,
        providers: Sequence[StructuredPlannerProvider],
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if len(providers) > MAX_PLANNER_PROVIDERS:
            raise ValueError(
                f"At most {MAX_PLANNER_PROVIDERS} planner providers are allowed."
            )
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("Planner timeout must be greater than 0 and at most 60s.")
        for provider in providers:
            if not isinstance(provider, StructuredPlannerProvider):
                raise TypeError(
                    "Each planner provider must implement generate_structured()."
                )
        self._providers = tuple(providers)
        self._timeout_seconds = float(timeout_seconds)

    def plan(
        self,
        raw_request: str,
        *,
        context: PlannerPromptContext | None = None,
        request_id: str | None = None,
    ) -> SemanticPlannerResult:
        """Request and strictly validate one semantic plan."""

        prompt = build_semantic_planner_prompt(raw_request, context=context)
        if not self._providers:
            raise SemanticPlannerError(())

        failures: list[PlannerAttemptFailure] = []
        started = time.perf_counter()
        for index, provider in enumerate(self._providers, start=1):
            provider_label = f"provider-{index}"
            request = PlannerProviderRequest(
                purpose=ModelCallPurpose.PLANNER,
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
                response_schema=deepcopy(prompt.response_schema),
                timeout_seconds=self._timeout_seconds,
                request_id=request_id,
            )
            try:
                response = provider.generate_structured(request)
                if not isinstance(response, PlannerProviderResponse):
                    raise SemanticPlanWireError(
                        "Provider returned an invalid response contract."
                    )
                provider_label = _bounded_identity(response.provider, provider_label)
                parsed = _parse_provider_payload(response.payload)
                model_label = _bounded_identity(response.model, "unknown")
                raw_usage = _copy_raw_usage(response.raw_usage)
            except TimeoutError as exc:
                failures.append(
                    _failure(provider_label, PlannerFailureReason.TIMEOUT, exc)
                )
                continue
            except (ConnectionError, OSError) as exc:
                failures.append(
                    _failure(
                        provider_label,
                        PlannerFailureReason.PROVIDER_UNAVAILABLE,
                        exc,
                    )
                )
                continue
            except SemanticPlanWireError as exc:
                failures.append(
                    _failure(
                        provider_label,
                        PlannerFailureReason.INVALID_OUTPUT,
                        exc,
                    )
                )
                continue
            except Exception as exc:
                failures.append(
                    _failure(provider_label, PlannerFailureReason.PROVIDER_ERROR, exc)
                )
                continue

            return SemanticPlannerResult(
                plan=parsed.plan,
                provider=provider_label,
                model=model_label,
                raw_usage=raw_usage,
                purpose=ModelCallPurpose.PLANNER,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                final_answer=parsed.final_answer,
            )

        raise SemanticPlannerError(tuple(failures))

    def plan_safely(
        self,
        raw_request: str,
        *,
        context: PlannerPromptContext | None = None,
        request_id: str | None = None,
    ) -> SemanticPlannerOutcome:
        """Return one structured outcome without inventing fallback semantics.

        Provider failover remains bounded to one call per configured provider;
        this method performs no repair prompt and no retry loop.
        """

        try:
            result = self.plan(
                raw_request,
                context=context,
                request_id=request_id,
            )
        except SemanticPlannerError as exc:
            return SemanticPlannerOutcome(
                status=SemanticPlannerOutcomeStatus.FAILED,
                reason=_outcome_reason_for_failure(exc.reason),
                failures=exc.failures,
            )
        return _classify_semantic_plan(result)


def _classify_semantic_plan(result: SemanticPlannerResult) -> SemanticPlannerOutcome:
    plan = result.plan
    if plan.target.kind is TargetReferenceKind.AMBIGUOUS:
        return _clarification_outcome(
            result,
            SemanticPlannerOutcomeReason.AMBIGUOUS_TARGET,
            "target",
        )
    if (
        plan.clarification is ClarificationState.REQUIRED
        or plan.route is SemanticPlanRoute.CLARIFY
    ):
        return _clarification_outcome(
            result,
            SemanticPlannerOutcomeReason.CLARIFICATION_REQUIRED,
            plan.clarification_field or "request",
        )

    if _is_contradictory(plan):
        return SemanticPlannerOutcome(
            status=SemanticPlannerOutcomeStatus.FAILED,
            reason=SemanticPlannerOutcomeReason.CONTRADICTORY_PLAN,
            result=result,
        )

    if _is_uncertain(plan):
        return SemanticPlannerOutcome(
            status=SemanticPlannerOutcomeStatus.UNSUPPORTED,
            reason=SemanticPlannerOutcomeReason.PLANNER_UNCERTAIN,
            result=result,
        )

    if _is_incomplete(plan):
        field = _missing_semantic_field(plan)
        if field is not None:
            return _clarification_outcome(
                result,
                SemanticPlannerOutcomeReason.INCOMPLETE_PLAN,
                field,
            )
        return SemanticPlannerOutcome(
            status=SemanticPlannerOutcomeStatus.UNSUPPORTED,
            reason=SemanticPlannerOutcomeReason.INCOMPLETE_PLAN,
            result=result,
        )

    return SemanticPlannerOutcome(
        status=SemanticPlannerOutcomeStatus.VALID,
        reason=SemanticPlannerOutcomeReason.PLAN_VALID,
        plan=plan,
        result=result,
    )


def _clarification_outcome(
    result: SemanticPlannerResult,
    reason: SemanticPlannerOutcomeReason,
    field: str,
) -> SemanticPlannerOutcome:
    return SemanticPlannerOutcome(
        status=SemanticPlannerOutcomeStatus.CLARIFY,
        reason=reason,
        plan=result.plan,
        clarification_field=field,
        result=result,
    )


def _is_contradictory(plan: SemanticPlan) -> bool:
    target_has_value = plan.target.value is not None
    target_forbids_value = plan.target.kind in {
        TargetReferenceKind.UNSPECIFIED,
        TargetReferenceKind.UNKNOWN,
    }
    direct_with_execution = (
        plan.route is SemanticPlanRoute.DIRECT_ANSWER
        and plan.execution_intent
        in {
            ExecutionIntent.INSPECT_READ_ONLY,
            ExecutionIntent.MUTATE_ENVIRONMENT,
        }
    )
    conflicting_sources = bool(
        set(plan.source_constraints).intersection(plan.excluded_sources)
    )
    stray_clarification_field = (
        plan.clarification is ClarificationState.NOT_REQUIRED
        and plan.clarification_field is not None
    )
    return (
        (target_forbids_value and target_has_value)
        or direct_with_execution
        or conflicting_sources
        or stray_clarification_field
    )


def _is_uncertain(plan: SemanticPlan) -> bool:
    return (
        plan.route is SemanticPlanRoute.UNKNOWN
        or plan.domain is RequestDomain.UNKNOWN
        or plan.execution_intent is ExecutionIntent.UNKNOWN
        or plan.target.kind is TargetReferenceKind.UNKNOWN
        or plan.clarification is ClarificationState.UNKNOWN
        or SourceConstraint.UNKNOWN in plan.source_constraints
    )


def _is_incomplete(plan: SemanticPlan) -> bool:
    return (
        plan.route is SemanticPlanRoute.UNSPECIFIED
        or plan.domain is RequestDomain.UNSPECIFIED
        or plan.execution_intent is ExecutionIntent.UNSPECIFIED
        or plan.clarification is ClarificationState.UNSPECIFIED
        or SourceConstraint.UNSPECIFIED in plan.source_constraints
        or (
            _requires_target(plan)
            and (
                plan.target.kind is TargetReferenceKind.UNSPECIFIED
                or (
                    plan.target.kind
                    in {
                        TargetReferenceKind.EXPLICIT,
                        TargetReferenceKind.INHERITED,
                    }
                    and plan.target.value is None
                )
            )
        )
    )


def _missing_semantic_field(plan: SemanticPlan) -> str | None:
    if (
        _requires_target(plan)
        and plan.target.kind
        in {
            TargetReferenceKind.UNSPECIFIED,
            TargetReferenceKind.EXPLICIT,
            TargetReferenceKind.INHERITED,
        }
        and plan.target.value is None
    ):
        return "target"
    return None


def _requires_target(plan: SemanticPlan) -> bool:
    return (
        plan.route is SemanticPlanRoute.CAPABILITY_ASSISTED
        and plan.domain is RequestDomain.ENVIRONMENT
    )


def _outcome_reason_for_failure(
    reason: PlannerFailureReason,
) -> SemanticPlannerOutcomeReason:
    return {
        PlannerFailureReason.NO_PROVIDER: SemanticPlannerOutcomeReason.NO_PROVIDER,
        PlannerFailureReason.TIMEOUT: SemanticPlannerOutcomeReason.PROVIDER_TIMEOUT,
        PlannerFailureReason.PROVIDER_UNAVAILABLE: (
            SemanticPlannerOutcomeReason.PROVIDER_UNAVAILABLE
        ),
        PlannerFailureReason.PROVIDER_ERROR: (
            SemanticPlannerOutcomeReason.PROVIDER_ERROR
        ),
        PlannerFailureReason.INVALID_OUTPUT: (
            SemanticPlannerOutcomeReason.MALFORMED_OUTPUT
        ),
    }[reason]


def _parse_provider_payload(payload: object) -> PlannerWireOutput:
    if isinstance(payload, dict):
        return planner_output_from_wire(payload)
    if isinstance(payload, (str, bytes)):
        return planner_output_from_json(payload)
    raise SemanticPlanWireError(
        "Provider payload must be a planner-output object or JSON text."
    )


def _failure(
    provider: str,
    reason: PlannerFailureReason,
    exc: Exception,
) -> PlannerAttemptFailure:
    message = " ".join(redact_sensitive(str(exc)).split()) or type(exc).__name__
    return PlannerAttemptFailure(
        provider=provider,
        reason=reason,
        message=message[:MAX_PLANNER_ERROR_CHARS],
    )


def _bounded_identity(value: object, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    return redact_sensitive(value.strip())[:80]


def _copy_raw_usage(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SemanticPlanWireError("Provider raw_usage must be a mapping or null.")
    if len(value) > 32:
        raise SemanticPlanWireError("Provider raw_usage exceeds 32 fields.")
    if any(not isinstance(key, str) for key in value):
        raise SemanticPlanWireError("Provider raw_usage keys must be strings.")
    return dict(value)


__all__ = [
    "MAX_PLANNER_ERROR_CHARS",
    "ModelCallPurpose",
    "PlannerAttemptFailure",
    "PlannerFailureReason",
    "PlannerProviderRequest",
    "PlannerProviderResponse",
    "SemanticPlannerAdapter",
    "SemanticPlannerError",
    "SemanticPlannerOutcome",
    "SemanticPlannerOutcomeReason",
    "SemanticPlannerOutcomeStatus",
    "SemanticPlannerResult",
    "StructuredPlannerProvider",
]
