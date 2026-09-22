"""Provider-neutral model boundary."""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from orion.contracts import (
    AssistantDelta,
    ContextMessage,
    ModelTurn,
    ModelTurnCompleted,
    ReasoningDelta,
    ToolCallDelta,
    ToolDefinition,
)

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
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_type: str = Field(pattern=r"^openai_compatible$")
    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key: str | None = None
    reasoning_mode: ReasoningMode = ReasoningMode.AUTO


class ModelBackendErrorKind(StrEnum):
    """Safe, provider-neutral categories for model backend failures."""

    CONNECTION = "connection"
    EMPTY_TURN = "empty_turn"
    INCOMPLETE_STREAM = "incomplete_stream"
    MALFORMED_STREAM = "malformed_stream"
    PROTOCOL = "protocol"
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
    ) -> None:
        super().__init__(message)
        self.kind = kind


class ModelBackend(ABC):
    @abstractmethod
    def stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Yield normalized deltas and finish with one canonical reconstructed turn."""

    async def complete(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> ModelTurn:
        """Convenience collector for callers that do not need public streaming."""
        async for event in self.stream(messages, tools, settings, cancellation):
            if isinstance(event, ModelTurnCompleted):
                return event.turn
        raise ModelBackendError("Model stream ended without a completed turn.")
