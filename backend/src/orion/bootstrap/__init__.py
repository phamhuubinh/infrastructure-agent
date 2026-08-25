"""Explicit composition root for Orion's local Chat application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from orion.access import LocalAccessAdapter
from orion.chat.runtime import ChatRuntime
from orion.models.backend import ModelBackend
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.calculator import calculate, calculator_definition
from orion.tool_runtime.registry import ToolRegistration, ToolRegistry, ToolRegistryBuilder


@dataclass(frozen=True)
class OrionApplication:
    """Dependencies constructed once and handed to boundary adapters."""

    store: SQLiteStore
    access: LocalAccessAdapter
    backend: ModelBackend
    registry: ToolRegistry
    runtime: ChatRuntime


def build_application(
    database_path: Path | None = None,
    backend: ModelBackend | None = None,
    tool_registrations: tuple[ToolRegistration, ...] | None = None,
) -> OrionApplication:
    """Build the complete local application with one registry snapshot."""
    resolved_path = database_path or Path(os.getenv("ORION_DATABASE_PATH", "data/orion.db"))
    store = SQLiteStore(resolved_path)
    _configure_model_from_environment(store)
    access = LocalAccessAdapter()
    registry_builder = ToolRegistryBuilder()
    for registration in tool_registrations or (
        ToolRegistration(definition=calculator_definition(), handler=calculate),
    ):
        registry_builder.register(registration.definition, registration.handler)
    registry = registry_builder.freeze()
    selected_backend = backend or OpenAICompatibleBackend()
    runtime = ChatRuntime(store, selected_backend, registry, access)
    return OrionApplication(
        store=store,
        access=access,
        backend=selected_backend,
        registry=registry,
        runtime=runtime,
    )


def _configure_model_from_environment(store: SQLiteStore) -> None:
    if store.active_model_config() is not None:
        return
    base_url, model_id = os.getenv("ORION_MODEL_BASE_URL"), os.getenv("ORION_MODEL_ID")
    if base_url and model_id:
        store.upsert_model_config(
            "openai_compatible", base_url, model_id, os.getenv("ORION_MODEL_API_KEY")
        )
