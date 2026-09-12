"""Explicit composition root for Orion's local Chat application."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from orion.access import LocalAccessAdapter
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import ChatRuntime
from orion.integrations import (
    DuckDuckGoInternetClient,
    GrafanaClient,
    InternetClient,
    LinuxExecutor,
    SearxngInternetClient,
    TargetCatalog,
    ZabbixClient,
)
from orion.knowledge import KnowledgeService, knowledge_registrations
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.ports import Chunker, DocumentParser
from orion.models.backend import ModelBackend, ModelStreamSettings, ReasoningMode
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.observability import ApplicationLog
from orion.paths import database_path as default_database_path
from orion.persistence.sqlite import SQLiteStore
from orion.projects import ProjectService
from orion.tool_runtime.calculator import calculate, calculator_definition
from orion.tool_runtime.infrastructure import infrastructure_registrations
from orion.tool_runtime.internet import internet_registrations
from orion.tool_runtime.mutation_authorization import (
    MutationAuthorizationConfigurationError,
    MutationAuthorizationPolicy,
)
from orion.tool_runtime.registry import ToolRegistration, ToolRegistry, ToolRegistryBuilder


@dataclass(frozen=True)
class OrionApplication:
    """Dependencies constructed once and handed to boundary adapters."""

    store: SQLiteStore
    access: LocalAccessAdapter
    backend: ModelBackend
    registry: ToolRegistry
    knowledge: KnowledgeService
    projects: ProjectService
    internet: InternetClient
    runtime: ChatRuntime


def build_application(
    database_path: Path | None = None,
    backend: ModelBackend | None = None,
    tool_registrations: tuple[ToolRegistration, ...] | None = None,
    internet_client: InternetClient | None = None,
    infrastructure_catalog: TargetCatalog | None = None,
    linux_executor: LinuxExecutor | None = None,
    grafana_client: GrafanaClient | None = None,
    zabbix_client: ZabbixClient | None = None,
    knowledge_parser: DocumentParser | None = None,
    knowledge_chunker: Chunker | None = None,
    blocked_tool_operation_kinds: frozenset[str] = frozenset(),
) -> OrionApplication:
    """Build the complete local application with one registry snapshot."""
    stream_settings = ModelStreamSettings.from_environment()
    infrastructure_config = _infrastructure_configuration()
    resolved_path = database_path or default_database_path()
    store = SQLiteStore(resolved_path)
    _configure_model_from_environment(store)
    access = LocalAccessAdapter()
    registry_builder = ToolRegistryBuilder()
    knowledge = KnowledgeService(
        store,
        LocalBlobStore(resolved_path.parent / "blobs"),
        parser=knowledge_parser,
        chunker=knowledge_chunker,
    )
    knowledge.reconcile_incomplete()
    projects = ProjectService(store)
    internet = internet_client or _internet_client_from_environment()
    infrastructure_catalog = infrastructure_catalog or (
        TargetCatalog.from_mapping(infrastructure_config)
        if infrastructure_config is not None
        else TargetCatalog.from_environment()
    )
    for registration in tool_registrations or (
        ToolRegistration(definition=calculator_definition(), handler=calculate),
    ):
        registry_builder.register(registration.definition, registration.handler)
    for registration in knowledge_registrations(knowledge):
        registry_builder.register(registration.definition, registration.handler)
    for registration in internet_registrations(internet):
        registry_builder.register(registration.definition, registration.handler)
    for registration in infrastructure_registrations(
        infrastructure_catalog,
        linux=linux_executor,
        grafana=grafana_client,
        zabbix=zabbix_client,
    ):
        registry_builder.register(registration.definition, registration.handler)
    registry = registry_builder.freeze()
    try:
        authorization = MutationAuthorizationPolicy.from_mapping(
            infrastructure_config or {},
            registry.definitions(),
            lambda family, target_ref: _target_is_configured(
                infrastructure_catalog, family, target_ref
            ),
        )
    except MutationAuthorizationConfigurationError:
        store.close()
        raise
    selected_backend = backend or OpenAICompatibleBackend(stream_settings)
    diagnostic_sink = (
        BoundedModelInputDiagnostics() if os.getenv("ORION_RUNTIME_DIAGNOSTICS") == "qa" else None
    )
    runtime = ChatRuntime(
        store,
        selected_backend,
        registry,
        access,
        infrastructure_catalog.model_context(),
        ApplicationLog(Path(os.environ["ORION_LOG_PATH"])) if os.getenv("ORION_LOG_PATH") else None,
        blocked_tool_operation_kinds,
        diagnostic_sink,
        mutation_authorization=authorization,
    )
    return OrionApplication(
        store=store,
        access=access,
        backend=selected_backend,
        registry=registry,
        knowledge=knowledge,
        projects=projects,
        internet=internet,
        runtime=runtime,
    )


def _configure_model_from_environment(store: SQLiteStore) -> None:
    if store.model_configs():
        return
    base_url, model_id = os.getenv("ORION_MODEL_BASE_URL"), os.getenv("ORION_MODEL_ID")
    if base_url and model_id:
        store.create_model_config(
            "openai_compatible",
            base_url,
            model_id,
            os.getenv("ORION_MODEL_API_KEY"),
            ReasoningMode(os.getenv("ORION_MODEL_REASONING_MODE", "auto")).value,
        )


def _internet_client_from_environment() -> InternetClient:
    search_url = os.getenv("ORION_INTERNET_SEARCH_URL")
    if not search_url:
        return DuckDuckGoInternetClient()
    return SearxngInternetClient(search_url)


def _target_is_configured(catalog: TargetCatalog, family: str, target_ref: str) -> bool:
    return any(target.target_ref == target_ref for target in catalog.targets(family))


def _infrastructure_configuration() -> dict[str, object] | None:
    path = os.getenv("ORION_INFRASTRUCTURE_CONFIG")
    if path is None:
        return None
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise MutationAuthorizationConfigurationError(
            "Invalid production infrastructure configuration: expected a readable JSON object."
        ) from None
    if not isinstance(raw, dict):
        raise MutationAuthorizationConfigurationError(
            "Invalid production infrastructure configuration: expected a JSON object."
        )
    return raw
