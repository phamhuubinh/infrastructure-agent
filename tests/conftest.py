from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from orion.contracts import ContextMessage, ModelTurn, ToolDefinition
from orion.models.backend import ModelBackend, ModelSettings
from orion.persistence.sqlite import SQLiteStore
from orion.runtime.chat_runtime import ChatRuntime
from orion.tools.calculator.tool import calculate, calculator_definition
from orion.tools.registry import ToolRegistry


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class ScriptedBackend(ModelBackend):
    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self.turns = list(turns)
        self.calls: list[tuple[tuple[ContextMessage, ...], tuple[ToolDefinition, ...]]] = []

    async def complete(self, messages, tools, settings: ModelSettings, cancellation) -> ModelTurn:  # type: ignore[no-untyped-def]
        self.calls.append((messages, tools))
        return self.turns.pop(0)


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    instance = SQLiteStore(tmp_path / "orion.db")
    instance.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    yield instance
    instance.close()


def runtime(
    store: SQLiteStore, backend: ModelBackend, registry: ToolRegistry | None = None
) -> ChatRuntime:
    registered = registry or ToolRegistry()
    if not registered.definitions():
        registered.register(calculator_definition(), calculate)
    return ChatRuntime(store, backend, registered)
