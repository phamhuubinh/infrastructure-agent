"""Provider-neutral model boundary."""

from __future__ import annotations

import asyncio
import os
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ContextMessage,
    ModelTurn,
    ModelTurnCompleted,
    ProviderContinuation,
    ReasoningDelta,
    RuntimeScope,
    ToolCallDelta,
    ToolDefinition,
)
from orion.contracts.profiles import ModelProfile
from orion.security import SecretStreamRedactor, protected_value_present, redact_text

ModelStreamEvent = AssistantDelta | ReasoningDelta | ToolCallDelta | ModelTurnCompleted


@dataclass(frozen=True)
class ModelRequest:
    """Provider-neutral input with instructions separate from conversation data.

    Providers serialize this as one leading system message followed by the
    user/assistant/tool conversation.  Keeping the split explicit prevents a
    runtime instruction from being appended after a tool or assistant message.
    """

    system_instructions: str
    messages: tuple[ContextMessage, ...]
    tools: tuple[ToolDefinition, ...]

    def __post_init__(self) -> None:
        if any(message.role == "system" for message in self.messages):
            raise ValueError("ModelRequest conversation messages cannot contain system roles.")

    def provider_messages(self) -> tuple[ContextMessage, ...]:
        leading = (
            (ContextMessage(role="system", content=self.system_instructions),)
            if self.system_instructions
            else ()
        )
        return (*leading, *self.messages)


@dataclass(frozen=True)
class ModelStreamSettings:
    """Validated provider transport settings, distinct from the request budget."""

    timeout_seconds: float = 30

    def __post_init__(self) -> None:
        if not 1 <= self.timeout_seconds <= 300:
            raise ValueError(
                "ORION_MODEL_STREAM_TIMEOUT_SECONDS must be between 1 and 300 seconds."
            )

    @classmethod
    def from_environment(cls) -> ModelStreamSettings:
        value = os.getenv("ORION_MODEL_STREAM_TIMEOUT_SECONDS")
        if value is None:
            return cls()
        try:
            timeout_seconds = float(value)
        except ValueError as error:
            raise ValueError(
                "ORION_MODEL_STREAM_TIMEOUT_SECONDS must be a number of seconds."
            ) from error
        return cls(timeout_seconds=timeout_seconds)


class ReasoningMode(StrEnum):
    """Provider-neutral request preference for models that support reasoning controls."""

    AUTO = "auto"
    ENABLED = "enabled"
    DISABLED = "disabled"


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    provider_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    reasoning_mode: ReasoningMode = ReasoningMode.AUTO
    profile: ModelProfile | None = None
    # Request-local protocol data only; never profile persistence or diagnostics.
    provider_continuation: ProviderContinuation | None = Field(
        default=None, exclude=True, repr=False
    )
    request_binding: str = Field(default_factory=lambda: uuid.uuid4().hex, exclude=True, repr=False)
    runtime_scope: RuntimeScope | None = Field(default=None, exclude=True, repr=False)


class ModelBackendErrorKind(StrEnum):
    """Safe, provider-neutral categories for model backend failures."""

    CONNECTION = "connection"
    EMPTY_TURN = "empty_turn"
    INCOMPLETE_STREAM = "incomplete_stream"
    MALFORMED_STREAM = "malformed_stream"
    PROTOCOL = "protocol"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
    UPSTREAM_HTTP = "upstream_http"
    UPSTREAM_STREAM_ERROR = "upstream_stream_error"


class ModelBackendError(RuntimeError):
    """A clear, safely classified provider error at the adapter boundary."""

    def __init__(
        self,
        message: str,
        *,
        kind: ModelBackendErrorKind = ModelBackendErrorKind.UNKNOWN,
        retry_safe: bool = False,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        # Only adapters can attest that no request reached the upstream service.
        self.retry_safe = retry_safe


async def validated_model_stream(
    events: AsyncIterator[ModelStreamEvent],
    *,
    credential: str | None = None,
) -> AsyncGenerator[ModelStreamEvent, None]:
    """Validate normalized streams, including structurally compatible backends."""
    completed = False
    sensitive = (credential,) if credential else ()
    redactor = SecretStreamRedactor(sensitive)
    try:
        async for event in events:
            if completed or not isinstance(
                event, (AssistantDelta, ReasoningDelta, ToolCallDelta, ModelTurnCompleted)
            ):
                raise ModelBackendError(
                    "Model stream violated the normalized event protocol.",
                    kind=ModelBackendErrorKind.PROTOCOL,
                )
            if isinstance(event, AssistantDelta):
                visible = redactor.feed(event.content)
                if visible:
                    yield AssistantDelta(content=visible)
                continue
            completed = isinstance(event, ModelTurnCompleted)
            if isinstance(event, ModelTurnCompleted):
                if protected_value_present(
                    [call.model_dump(mode="json") for call in event.turn.tool_calls], sensitive
                ):
                    raise ModelBackendError(
                        "Model tool call contains protected credential material.",
                        kind=ModelBackendErrorKind.PROTOCOL,
                    )
                tail = redactor.finish()
                if tail:
                    yield AssistantDelta(content=tail)
                assistant = event.turn.assistant
                if assistant is not None:
                    safe = AssistantMessage(
                        content=redact_text(assistant.content, sensitive=sensitive),
                        citation_source_ref_ids=tuple(
                            redact_text(v, sensitive=sensitive)
                            for v in assistant.citation_source_ref_ids
                        ),
                        citation_evidence_refs=tuple(
                            redact_text(v, sensitive=sensitive)
                            for v in assistant.citation_evidence_refs
                        ),
                    )
                    event = event.model_copy(
                        update={"turn": event.turn.model_copy(update={"assistant": safe})}
                    )
            yield event
        if not completed:
            raise ModelBackendError(
                "Model stream ended without a completed turn.",
                kind=ModelBackendErrorKind.INCOMPLETE_STREAM,
            )
    finally:
        # Rejecting a malformed stream must also release its HTTP/process context.
        close = getattr(events, "aclose", None)
        if close is not None:
            await close()


class ModelBackend(ABC):
    requires_credential: bool = False

    def validate_settings(self, settings: ModelSettings) -> None:
        """Adapters may reject unsupported controls before credentials/transport."""
        return None

    @abstractmethod
    def stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Yield normalized deltas and finish with one canonical reconstructed turn."""

    async def validated_stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Enforce the normalized protocol before a caller may dispatch tools."""
        async with aclosing(
            validated_model_stream(
                self.stream(messages, tools, settings, cancellation), credential=settings.api_key
            )
        ) as events:
            async for event in events:
                yield event

    async def complete(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> ModelTurn:
        """Convenience collector for callers that do not need public streaming."""
        turn: ModelTurn | None = None
        async for event in self.validated_stream(messages, tools, settings, cancellation):
            if isinstance(event, ModelTurnCompleted):
                turn = event.turn
        assert turn is not None  # validated_stream rejects a missing terminal event.
        return turn
