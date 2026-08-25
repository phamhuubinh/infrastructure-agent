from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from orion.access import LocalAccessAdapter
from orion.chat.runtime import ChatRuntime
from orion.contracts import (
    AssistantDelta,
    ContextMessage,
    ModelTurn,
    ModelTurnCompleted,
    ToolDefinition,
)
from orion.models.backend import ModelBackend, ModelSettings
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.calculator import calculate, calculator_definition
from orion.tool_runtime.registry import ToolRegistry, ToolRegistryBuilder


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class ScriptedBackend(ModelBackend):
    def __init__(
        self, turns: Sequence[ModelTurn], deltas: Sequence[Sequence[str]] | None = None
    ) -> None:
        self.turns = list(turns)
        self.deltas = list(deltas or ())
        self.calls: list[tuple[tuple[ContextMessage, ...], tuple[ToolDefinition, ...]]] = []

    async def stream(self, messages, tools, settings: ModelSettings, cancellation):  # type: ignore[no-untyped-def]
        self.calls.append((messages, tools))
        for delta in self.deltas.pop(0) if self.deltas else ():
            yield AssistantDelta(content=delta)
        yield ModelTurnCompleted(turn=self.turns.pop(0))


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    instance = SQLiteStore(tmp_path / "orion.db")
    instance.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    yield instance
    instance.close()


def runtime(
    store: SQLiteStore, backend: ModelBackend, registry: ToolRegistry | None = None
) -> ChatRuntime:
    registered = registry or ToolRegistryBuilder().freeze()
    if not registered.definitions():
        builder = ToolRegistryBuilder()
        builder.register(calculator_definition(), calculate)
        registered = builder.freeze()
    return ChatRuntime(store, backend, registered, LocalAccessAdapter())
