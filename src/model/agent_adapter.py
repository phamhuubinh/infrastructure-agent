"""Provider-neutral model adapter for the canonical Orion agent protocol.

This layer owns model I/O only. It does not interpret user language, grant
authority, validate capabilities, resolve targets/sources, or execute actions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from src.agent.contracts import AgentDecision, ContractError
from src.model.protocol.agent_transport import (
    agent_decision_json_schema,
    parse_agent_decision_payload,
)

MAX_AGENT_PROVIDERS = 8
MAX_PROVIDER_IDENTITY_CHARS = 128
MAX_PROVIDER_ERROR_CHARS = 240


@dataclass(frozen=True, slots=True)
class AgentProviderRequest:
    """One provider-neutral structured model request."""

    system_prompt: str
    user_prompt: str
    response_schema: dict[str, object]
    timeout_seconds: float
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentProviderResponse:
    """Provider output before canonical decision parsing."""

    payload: object
    provider: str
    model: str
    raw_usage: Mapping[str, object] | None = None


@runtime_checkable
class StructuredAgentProvider(Protocol):
    """Provider contract with no execution methods."""

    def generate_agent_decision(
        self,
        request: AgentProviderRequest,
    ) -> AgentProviderResponse:
        """Return one structured agent decision or raise a provider error."""


class AgentModelFailureReason(str, Enum):
    NO_PROVIDER = "no_provider"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True, slots=True)
class AgentModelAttemptFailure:
    provider: str
    reason: AgentModelFailureReason
    message: str
    model: str | None = None


class AgentModelError(RuntimeError):
    """All configured providers failed to return one valid decision."""

    def __init__(
        self,
        failures: tuple[AgentModelAttemptFailure, ...],
    ) -> None:
        self.failures = failures
        self.reason = (
            AgentModelFailureReason.NO_PROVIDER
            if not failures
            else failures[-1].reason
        )

        if not failures:
            message = "No agent model provider is configured."
        else:
            details = "; ".join(
                f"{failure.provider}:{failure.reason.value}:{failure.message}"
                for failure in failures
            )
            message = f"Agent model decision failed: {details}"

        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AgentDecisionResult:
    decision: AgentDecision
    provider: str
    model: str
    raw_usage: Mapping[str, object] | None
    provider_attempt_count: int


class AgentModelAdapter:
    """Request one canonical decision with bounded provider failover."""

    def __init__(
        self,
        providers: Sequence[StructuredAgentProvider],
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if len(providers) > MAX_AGENT_PROVIDERS:
            raise ValueError(
                f"At most {MAX_AGENT_PROVIDERS} agent providers are allowed."
            )

        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ValueError(
                "Agent model timeout must be greater than 0 and at most 120s."
            )

        for provider in providers:
            if not isinstance(provider, StructuredAgentProvider):
                raise TypeError(
                    "Each agent provider must implement "
                    "generate_agent_decision()."
                )

        self._providers = tuple(providers)
        self._timeout_seconds = float(timeout_seconds)

    def decide(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        selected_capability_schema: Mapping[str, object] | None = None,
        request_id: str | None = None,
    ) -> AgentDecisionResult:
        """Return one strictly parsed canonical decision."""

        if not isinstance(system_prompt, str) or not system_prompt:
            raise ValueError("system_prompt must be a non-empty string.")

        if not isinstance(user_prompt, str) or not user_prompt:
            raise ValueError("user_prompt must be a non-empty string.")

        if request_id is not None and (
            not isinstance(request_id, str) or not request_id
        ):
            raise ValueError("request_id must be a non-empty string or None.")

        response_schema = agent_decision_json_schema(
            selected_capability_schema
        )

        if not self._providers:
            raise AgentModelError(())

        failures: list[AgentModelAttemptFailure] = []

        for index, provider in enumerate(self._providers, start=1):
            provider_fallback = f"provider-{index}"
            request = AgentProviderRequest(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=deepcopy(response_schema),
                timeout_seconds=self._timeout_seconds,
                request_id=request_id,
            )

            try:
                response = provider.generate_agent_decision(request)
            except TimeoutError as exc:
                failures.append(
                    _failure(
                        provider_fallback,
                        AgentModelFailureReason.TIMEOUT,
                        exc,
                    )
                )
                continue
            except (ConnectionError, OSError) as exc:
                failures.append(
                    _failure(
                        provider_fallback,
                        AgentModelFailureReason.PROVIDER_UNAVAILABLE,
                        exc,
                    )
                )
                continue
            except Exception as exc:
                failures.append(
                    _failure(
                        provider_fallback,
                        AgentModelFailureReason.PROVIDER_ERROR,
                        exc,
                    )
                )
                continue

            if not isinstance(response, AgentProviderResponse):
                failures.append(
                    AgentModelAttemptFailure(
                        provider=provider_fallback,
                        reason=AgentModelFailureReason.INVALID_OUTPUT,
                        message="Provider returned an invalid response contract.",
                    )
                )
                continue

            provider_name = _bounded_identity(
                response.provider,
                provider_fallback,
            )
            model_name = _bounded_identity(response.model, "unknown")

            try:
                decision = parse_agent_decision_payload(response.payload)
                raw_usage = _copy_raw_usage(response.raw_usage)
            except (ContractError, TypeError, ValueError) as exc:
                failures.append(
                    _failure(
                        provider_name,
                        AgentModelFailureReason.INVALID_OUTPUT,
                        exc,
                        model=model_name,
                    )
                )
                continue

            return AgentDecisionResult(
                decision=decision,
                provider=provider_name,
                model=model_name,
                raw_usage=raw_usage,
                provider_attempt_count=index,
            )

        raise AgentModelError(tuple(failures))


def _bounded_identity(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback

    normalized = value.strip()
    if not normalized:
        return fallback

    return normalized[:MAX_PROVIDER_IDENTITY_CHARS]


def _copy_raw_usage(
    value: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if value is None:
        return None

    if not isinstance(value, Mapping):
        raise TypeError("raw_usage must be a mapping or None.")

    return dict(value)


def _failure(
    provider: str,
    reason: AgentModelFailureReason,
    exc: BaseException,
    *,
    model: str | None = None,
) -> AgentModelAttemptFailure:
    message = str(exc).replace("\n", " ").strip()
    if not message:
        message = exc.__class__.__name__

    return AgentModelAttemptFailure(
        provider=provider,
        reason=reason,
        message=message[:MAX_PROVIDER_ERROR_CHARS],
        model=model,
    )
