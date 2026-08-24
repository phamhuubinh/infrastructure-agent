"""Provider-neutral model boundary."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from orion.contracts import ContextMessage, ModelTurn, ToolDefinition


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
    async def complete(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> ModelTurn:
        """Return a provider-normalized turn without leaking native objects."""
