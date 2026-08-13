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
from src.pipeline.semantic_plan import SemanticPlan
from src.pipeline.semantic_plan_wire import (
    SemanticPlanWireError,
    semantic_plan_from_json,
    semantic_plan_from_wire,
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
    """Validated plan plus provider metadata kept outside the plan itself."""

    plan: SemanticPlan
    provider: str
    model: str
    raw_usage: Mapping[str, object] | None
    purpose: ModelCallPurpose
    latency_ms: float


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
                plan = _parse_provider_payload(response.payload)
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
            except RuntimeError as exc:
                failures.append(
                    _failure(provider_label, PlannerFailureReason.PROVIDER_ERROR, exc)
                )
                continue

            return SemanticPlannerResult(
                plan=plan,
                provider=provider_label,
                model=model_label,
                raw_usage=raw_usage,
                purpose=ModelCallPurpose.PLANNER,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )

        raise SemanticPlannerError(tuple(failures))


def _parse_provider_payload(payload: object) -> SemanticPlan:
    if isinstance(payload, dict):
        return semantic_plan_from_wire(payload)
    if isinstance(payload, (str, bytes)):
        return semantic_plan_from_json(payload)
    raise SemanticPlanWireError(
        "Provider payload must be a semantic-plan object or JSON text."
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
    "SemanticPlannerResult",
    "StructuredPlannerProvider",
]
