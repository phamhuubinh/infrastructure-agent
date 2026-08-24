"""Provider-neutral model adapter for the canonical Orion agent protocol.

This layer owns model I/O only. It does not interpret user language, grant
authority, validate capabilities, resolve targets/sources, or execute actions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from src.agent.contracts import AgentDecision, ContractError
from src.model.protocol.agent_transport import (
    agent_decision_json_schema,
    parse_agent_decision_payload,
)
from src.shared.redaction import redact_sensitive

MAX_AGENT_PROVIDERS = 8
MAX_PROVIDER_IDENTITY_CHARS = 128
MAX_PROVIDER_ERROR_CHARS = 240
_CANONICAL_DECISION_KEYS = frozenset(
    {
        "version",
        "kind",
        "goal",
        "category",
        "action",
        "answer",
        "question",
        "reason",
        "claims",
    }
)
_CANONICAL_DECISION_KINDS = frozenset(
    {"final", "discover", "action", "clarify", "refuse"}
)


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
    generation_diagnostics: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.raw_usage, Mapping):
            object.__setattr__(self, "raw_usage", dict(self.raw_usage))
        if isinstance(self.generation_diagnostics, Mapping):
            object.__setattr__(
                self,
                "generation_diagnostics",
                dict(self.generation_diagnostics),
            )


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
    diagnostics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", dict(self.diagnostics))


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
        response_schema: Mapping[str, object] | None = None,
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

        effective_response_schema = (
            deepcopy(dict(response_schema))
            if response_schema is not None
            else agent_decision_json_schema(
                selected_capability_schema
            )
        )

        if not self._providers:
            raise AgentModelError(())

        failures: list[AgentModelAttemptFailure] = []

        for index, provider in enumerate(self._providers, start=1):
            provider_fallback = f"provider-{index}"
            request = AgentProviderRequest(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=deepcopy(effective_response_schema),
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
                        diagnostics=_parse_diagnostics(
                            response.payload,
                            exc,
                            generation_diagnostics=response.generation_diagnostics,
                        ),
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
    diagnostics: Mapping[str, object] | None = None,
) -> AgentModelAttemptFailure:
    message = (
        redact_sensitive(str(exc))
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )
    if not message:
        message = exc.__class__.__name__

    return AgentModelAttemptFailure(
        provider=provider,
        reason=reason,
        message=message[:MAX_PROVIDER_ERROR_CHARS],
        model=model,
        diagnostics=dict(diagnostics or {}),
    )


def _parse_diagnostics(
    payload: object,
    error: BaseException,
    *,
    generation_diagnostics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return bounded parser diagnostics without retaining response content."""
    parsed: object | None = payload if isinstance(payload, Mapping) else None
    payload_length: int | None = None
    text_payload: str | None = None
    json_parseable = False
    if isinstance(payload, str):
        payload_length = len(payload.encode("utf-8"))
        text_payload = payload
        try:
            parsed = json.loads(payload)
            json_parseable = True
        except json.JSONDecodeError:
            parsed = None
    elif isinstance(payload, bytes):
        payload_length = len(payload)
        try:
            text_payload = payload.decode("utf-8")
            parsed = json.loads(text_payload)
            json_parseable = True
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None

    diagnostics: dict[str, object] = {
        "response_type": type(payload).__name__[:64],
        "response_length": payload_length,
        "parse_error_category": _parse_error_category(error),
        "schema_validation_error_path": None,
        "parser_error_path": None,
    }
    if text_payload is not None:
        diagnostics.update(
            _text_format_diagnostics(
                text_payload,
                json_parseable=json_parseable,
            )
        )
    safe_generation_diagnostics = _safe_generation_diagnostics(
        generation_diagnostics,
    )
    if safe_generation_diagnostics:
        diagnostics["provider_generation"] = safe_generation_diagnostics
    if not isinstance(parsed, Mapping):
        return diagnostics

    keys = {
        key
        for key in parsed
        if isinstance(key, str) and key in _CANONICAL_DECISION_KEYS
    }
    diagnostics["json_top_level_keys"] = sorted(keys)
    diagnostics["unknown_top_level_key_count"] = len(parsed) - len(keys)
    kind = parsed.get("kind")
    diagnostics["decision_kind"] = (
        kind if isinstance(kind, str) and kind in _CANONICAL_DECISION_KINDS else None
    )
    diagnostics["parser_error_path"] = _parser_error_path(error)
    return diagnostics


_GENERATION_INT_FIELDS = frozenset(
    {
        "usage_completion_tokens",
        "usage_prompt_tokens",
        "content_bytes_before_sanitization",
        "content_bytes_after_sanitization",
        "provider_http_status",
    }
)


def _safe_generation_diagnostics(
    value: Mapping[str, object] | None,
) -> dict[str, object]:
    """Copy only allowlisted provider control metadata into failure events."""

    if not isinstance(value, Mapping):
        return {}

    diagnostics: dict[str, object] = {}
    finish_reason = value.get("finish_reason")
    if isinstance(finish_reason, str) and _is_safe_provider_category(finish_reason):
        diagnostics["finish_reason"] = finish_reason
    elif finish_reason is None:
        diagnostics["finish_reason"] = None

    for key in _GENERATION_INT_FIELDS:
        item = value.get(key)
        if item is None:
            diagnostics[key] = None
        elif isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            diagnostics[key] = item

    stop_sequence_configured = value.get("stop_sequence_configured")
    if isinstance(stop_sequence_configured, bool):
        diagnostics["stop_sequence_configured"] = stop_sequence_configured
    return diagnostics


def _is_safe_provider_category(value: str) -> bool:
    return bool(value) and len(value) <= 64 and all(
        character.isascii() and (character.isalnum() or character in "_.-")
        for character in value
    )


def _text_format_diagnostics(
    value: str,
    *,
    json_parseable: bool,
) -> dict[str, object]:
    """Classify text structure only; never return model text or JSON values."""
    stripped = value.strip()
    folded = stripped.casefold()
    return {
        "json_parseable": json_parseable,
        "stripped_starts_with_object": stripped.startswith("{"),
        "stripped_ends_with_object": stripped.endswith("}"),
        "contains_markdown_code_fence": "```" in stripped,
        "contains_think_open_tag": "<think" in folded,
        "contains_think_close_tag": "</think" in folded,
        "leading_format": _leading_format(stripped, folded),
        "trailing_format": _trailing_format(stripped, folded),
        "json_object_candidate_count": _json_object_candidate_count(stripped),
    }


def _leading_format(value: str, folded: str) -> str:
    if not value:
        return "empty"
    if value.startswith("```"):
        return "code_fence"
    if folded.startswith("<think"):
        return "think_tag"
    if value.startswith("{"):
        return "json_object"
    if value.startswith("["):
        return "json_array"
    if value[0].isalnum():
        return "prose"
    return "other"


def _trailing_format(value: str, folded: str) -> str:
    if value.endswith("```"):
        return "code_fence"
    if folded.endswith("</think>"):
        return "think_tag"
    if value.endswith("}"):
        return "json_object_end"
    if value and (value[-1].isalnum() or value[-1] in ".?!"):
        return "prose"
    return "other"


def _json_object_candidate_count(value: str) -> int:
    """Count balanced brace spans while respecting JSON string escapes."""
    count = 0
    depth = 0
    in_string = False
    escaped = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}" and depth:
            depth -= 1
            if depth == 0:
                count += 1
    return count


def _parse_error_category(error: BaseException) -> str:
    if isinstance(error, json.JSONDecodeError):
        return "json_decode_error"
    if isinstance(error, ContractError):
        return "contract_error"
    if isinstance(error, TypeError):
        return "type_error"
    if isinstance(error, ValueError):
        return "value_error"
    return "parse_error"


def _parser_error_path(error: BaseException) -> str | None:
    """Classify a canonical parser failure without copying its message."""
    if not isinstance(error, ContractError):
        return None
    message = str(error)
    if message.startswith("action"):
        return "action"
    if message.startswith("final claim"):
        return "claims"
    if message.startswith("decision") or message.startswith("Only FINAL"):
        return "decision"
    return "protocol"
