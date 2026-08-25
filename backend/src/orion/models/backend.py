"""Provider-neutral model boundary."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel, ConfigDict, Field

from orion.contracts import (
    AssistantDelta,
    ContextMessage,
    ModelTurn,
    ModelTurnCompleted,
    ToolCallDelta,
    ToolDefinition,
)

ModelStreamEvent = AssistantDelta | ToolCallDelta | ModelTurnCompleted


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_type: str = Field(pattern=r"^openai_compatible$")
    base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key: str | None = None


class ModelBackendError(RuntimeError):
    """A clear provider/transport error at the adapter boundary."""


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
