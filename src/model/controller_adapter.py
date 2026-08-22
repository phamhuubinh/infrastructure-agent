"""Provider-neutral, fail-closed adapter for one Agent v2 decision.

This module is intentionally not wired into the current semantic-planner
runtime.  It owns only prompt construction, provider failover, strict contract
validation, and usage telemetry for the future controller loop.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from src.agent.controller_contracts import (
    AgentDecision,
    ControllerCallStage,
    ControllerContractError,
    agent_decision_from_json,
)
from src.model.protocol.controller_prompt import (
    ControllerContinuationInput,
    ControllerPromptContext,
    build_controller_prompt,
)
from src.model.reasoning_effort import (
    ModelRequestClass,
    ReasoningEffort,
    ReasoningEffortPolicy,
)
from src.model.usage_recorder import ModelUsageRecorder
from src.pipeline.hard_request_constraints import HardRequestConstraints
from src.shared.execution.command_result import redact_sensitive

MAX_CONTROLLER_PROVIDERS = 8
MAX_CONTROLLER_ERROR_CHARS = 160


class ControllerCallPurpose(str, Enum):
    """Usage purpose for the isolated Agent v2 controller call."""

    CONTROLLER = "controller"


@dataclass(frozen=True, slots=True)
class ControllerProviderRequest:
    """The complete non-executable request sent to one controller provider."""

    purpose: ControllerCallPurpose
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, object]
    timeout_seconds: float
    call_stage: ControllerCallStage = ControllerCallStage.FIRST_DECISION
    input_budget_class: str = "controller_first"
    input_budget_max_chars: int = 6_500
    actual_input_chars: int = 0
    estimated_input_tokens: int = 0
    optional_included: tuple[str, ...] = ()
    optional_dropped: tuple[str, ...] = ()
    request_id: str | None = None

    @property
    def reasoning_effort(self) -> ReasoningEffort:
        return ReasoningEffortPolicy.for_call(
            purpose=f"{self.purpose.value}.{self.call_stage.value}",
            request_class=ModelRequestClass.TRIVIAL,
        )


@dataclass(frozen=True, slots=True)
class ControllerProviderResponse:
    """Raw structured provider output before ``AgentDecision`` validation."""

    payload: object
    provider: str
    model: str
    raw_usage: Mapping[str, object] | None = None
    configured_effort: ReasoningEffort | None = None


@runtime_checkable
class StructuredControllerProvider(Protocol):
    """Narrow controller-provider protocol with no execution methods."""

    def generate_controller(
        self,
        request: ControllerProviderRequest,
    ) -> ControllerProviderResponse:
        """Return one structured response or raise a provider error."""


class ControllerFailureReason(str, Enum):
    NO_PROVIDER = "no_provider"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    INVALID_OUTPUT = "invalid_output"


class ControllerOutcomeStatus(str, Enum):
    VALID = "valid"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ControllerAttemptFailure:
    provider: str
    reason: ControllerFailureReason
    message: str
    model: str | None = None
    raw_usage: Mapping[str, object] | None = None
    latency_ms: float | None = None
    estimated_input_tokens: int | None = None
    configured_effort: str | None = None


class ControllerAdapterError(RuntimeError):
    """All controller providers failed without a fallback or repair parser."""

    def __init__(self, failures: tuple[ControllerAttemptFailure, ...]) -> None:
        self.failures = failures
        self.reason = (
            ControllerFailureReason.NO_PROVIDER if not failures else failures[-1].reason
        )
        if not failures:
            message = "No controller provider is configured."
        else:
            details = "; ".join(
                f"{item.provider}:{item.reason.value}:{item.message}"
                for item in failures
            )
            message = f"Controller decision failed: {details}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ControllerDecisionResult:
    decision: AgentDecision
    provider: str
    model: str
    raw_usage: Mapping[str, object] | None
    purpose: ControllerCallPurpose
    call_stage: ControllerCallStage
    latency_ms: float
    estimated_input_tokens: int
    input_budget_class: str
    input_budget_max_chars: int
    actual_input_chars: int
    optional_included: tuple[str, ...]
    optional_dropped: tuple[str, ...]
    configured_effort: str | None = None


@dataclass(frozen=True, slots=True)
class ControllerOutcome:
    status: ControllerOutcomeStatus
    result: ControllerDecisionResult | None = None
    failures: tuple[ControllerAttemptFailure, ...] = ()

    @property
    def decision(self) -> AgentDecision | None:
        return self.result.decision if self.result is not None else None


class ControllerAdapter:
    """Request one typed decision, bounded to one attempt per provider."""

    def __init__(
        self,
        providers: Sequence[StructuredControllerProvider],
        *,
        timeout_seconds: float = 30.0,
        usage_recorder: ModelUsageRecorder | None = None,
    ) -> None:
        if len(providers) > MAX_CONTROLLER_PROVIDERS:
            raise ValueError(
                f"At most {MAX_CONTROLLER_PROVIDERS} controller providers are allowed."
            )
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError(
                "Controller timeout must be greater than 0 and at most 60s."
            )
        for provider in providers:
            if not isinstance(provider, StructuredControllerProvider):
                raise TypeError(
                    "Each controller provider must implement generate_controller()."
                )
        if usage_recorder is not None and not isinstance(
            usage_recorder, ModelUsageRecorder
        ):
            raise TypeError("usage_recorder must be ModelUsageRecorder or None.")
        self._providers = tuple(providers)
        self._timeout_seconds = float(timeout_seconds)
        self._usage_recorder = usage_recorder

    def decide(
        self,
        raw_request: str,
        *,
        hard_constraints: HardRequestConstraints,
        context: ControllerPromptContext | None = None,
        continuation: ControllerContinuationInput | None = None,
        call_stage: ControllerCallStage = ControllerCallStage.FIRST_DECISION,
        request_id: str | None = None,
    ) -> ControllerDecisionResult:
        """Build, invoke, record, and strictly parse one controller decision."""

        prompt = build_controller_prompt(
            raw_request,
            hard_constraints=hard_constraints,
            context=context,
            continuation=continuation,
            call_stage=call_stage,
        )
        if not self._providers:
            raise ControllerAdapterError(())

        failures: list[ControllerAttemptFailure] = []
        started = time.perf_counter()
        for index, provider in enumerate(self._providers, start=1):
            provider_label = f"provider-{index}"
            model_label: str | None = None
            raw_usage: dict[str, object] | None = None
            configured_effort: ReasoningEffort | None = None
            attempt_started = time.perf_counter()
            request = ControllerProviderRequest(
                purpose=ControllerCallPurpose.CONTROLLER,
                call_stage=call_stage,
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
                response_schema=deepcopy(prompt.response_schema),
                timeout_seconds=self._timeout_seconds,
                input_budget_class=prompt.input_budget_class,
                input_budget_max_chars=prompt.input_budget_max_chars,
                actual_input_chars=prompt.actual_input_chars,
                estimated_input_tokens=prompt.estimated_input_tokens,
                optional_included=prompt.optional_included,
                optional_dropped=prompt.optional_dropped,
                request_id=request_id,
            )
            try:
                response = provider.generate_controller(request)
                if not isinstance(response, ControllerProviderResponse):
                    raise ControllerContractError(
                        "Provider returned an invalid response contract."
                    )
                provider_label = _bounded_identity(response.provider, provider_label)
                model_label = _bounded_identity(response.model, "unknown")
                raw_usage = _copy_raw_usage(response.raw_usage)
                configured_effort = response.configured_effort
                if configured_effort is not None and not isinstance(
                    configured_effort, ReasoningEffort
                ):
                    raise ControllerContractError(
                        "Provider configured_effort must be ReasoningEffort or null."
                    )
                self._record_usage(
                    raw_usage,
                    provider=provider_label,
                    model=model_label,
                    estimated_input_tokens=prompt.estimated_input_tokens,
                    configured_effort=configured_effort,
                    call_stage=call_stage,
                )
                decision = _parse_provider_payload(response.payload)
            except TimeoutError as exc:
                failures.append(
                    _failure(provider_label, ControllerFailureReason.TIMEOUT, exc)
                )
                continue
            except (ConnectionError, OSError) as exc:
                failures.append(
                    _failure(
                        provider_label,
                        ControllerFailureReason.PROVIDER_UNAVAILABLE,
                        exc,
                    )
                )
                continue
            except (ControllerContractError, TypeError, ValueError) as exc:
                failures.append(
                    _failure(
                        provider_label,
                        ControllerFailureReason.INVALID_OUTPUT,
                        exc,
                        model=model_label,
                        raw_usage=raw_usage,
                        latency_ms=round(
                            (time.perf_counter() - attempt_started) * 1000, 1
                        ),
                        estimated_input_tokens=prompt.estimated_input_tokens,
                        configured_effort=(
                            configured_effort.value
                            if configured_effort is not None
                            else None
                        ),
                    )
                )
                continue
            except Exception as exc:
                failures.append(
                    _failure(
                        provider_label, ControllerFailureReason.PROVIDER_ERROR, exc
                    )
                )
                continue

            return ControllerDecisionResult(
                decision=decision,
                provider=provider_label,
                model=model_label,
                raw_usage=raw_usage,
                purpose=ControllerCallPurpose.CONTROLLER,
                call_stage=call_stage,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                estimated_input_tokens=prompt.estimated_input_tokens,
                input_budget_class=prompt.input_budget_class,
                input_budget_max_chars=prompt.input_budget_max_chars,
                actual_input_chars=prompt.actual_input_chars,
                optional_included=prompt.optional_included,
                optional_dropped=prompt.optional_dropped,
                configured_effort=(
                    configured_effort.value if configured_effort is not None else None
                ),
            )
        raise ControllerAdapterError(tuple(failures))

    def decide_safely(self, *args: object, **kwargs: object) -> ControllerOutcome:
        """Return a bounded failure outcome without repair or semantic fallback."""

        try:
            result = self.decide(*args, **kwargs)
        except ControllerAdapterError as exc:
            return ControllerOutcome(
                status=ControllerOutcomeStatus.FAILED,
                failures=exc.failures,
            )
        return ControllerOutcome(status=ControllerOutcomeStatus.VALID, result=result)

    def _record_usage(
        self,
        raw_usage: Mapping[str, object] | None,
        *,
        provider: str,
        model: str,
        estimated_input_tokens: int,
        configured_effort: ReasoningEffort | None,
        call_stage: ControllerCallStage,
    ) -> None:
        if self._usage_recorder is None:
            return
        self._usage_recorder.record_mapping(
            raw_usage,
            purpose=ControllerCallPurpose.CONTROLLER.value,
            provider=provider,
            model=model,
            estimated_input_tokens=estimated_input_tokens,
            configured_effort=(
                configured_effort.value if configured_effort is not None else None
            ),
            call_stage=call_stage.value,
        )


def _parse_provider_payload(payload: object) -> AgentDecision:
    if isinstance(payload, dict):
        return AgentDecision.from_wire(payload)
    if isinstance(payload, (str, bytes)):
        return agent_decision_from_json(payload)
    raise ControllerContractError(
        "Provider payload must be an AgentDecision object or JSON text."
    )


def _failure(
    provider: str,
    reason: ControllerFailureReason,
    exc: Exception,
    *,
    model: str | None = None,
    raw_usage: Mapping[str, object] | None = None,
    latency_ms: float | None = None,
    estimated_input_tokens: int | None = None,
    configured_effort: str | None = None,
) -> ControllerAttemptFailure:
    message = " ".join(redact_sensitive(str(exc)).split()) or type(exc).__name__
    return ControllerAttemptFailure(
        provider=provider,
        reason=reason,
        message=message[:MAX_CONTROLLER_ERROR_CHARS],
        model=model,
        raw_usage=raw_usage,
        latency_ms=latency_ms,
        estimated_input_tokens=estimated_input_tokens,
        configured_effort=configured_effort,
    )


def _bounded_identity(value: object, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    return redact_sensitive(value.strip())[:80]


def _copy_raw_usage(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ControllerContractError("Provider raw_usage must be a mapping or null.")
    if len(value) > 32 or any(not isinstance(key, str) for key in value):
        raise ControllerContractError("Provider raw_usage is not a compact mapping.")
    return dict(value)


__all__ = [
    "ControllerAdapter",
    "ControllerAdapterError",
    "ControllerAttemptFailure",
    "ControllerCallPurpose",
    "ControllerDecisionResult",
    "ControllerFailureReason",
    "ControllerOutcome",
    "ControllerOutcomeStatus",
    "ControllerProviderRequest",
    "ControllerProviderResponse",
    "MAX_CONTROLLER_ERROR_CHARS",
    "StructuredControllerProvider",
]
