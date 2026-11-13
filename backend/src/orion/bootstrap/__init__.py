"""Explicit composition root for Orion's local Chat application."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from orion.access import LocalAccessAdapter
from orion.access.native import NativeAuthService
from orion.application.command_tools import command_registrations
from orion.application.commands import CommandService
from orion.application.models import ModelConfigurationService
from orion.application.requests import RequestService
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import ChatRuntime
from orion.endpoints.manager import EndpointManager
from orion.endpoints.persistence import EndpointStore
from orion.endpoints.tools import endpoint_registrations
from orion.integrations import (
    DuckDuckGoInternetClient,
    InternetClient,
    LinuxExecutor,
    SearxngInternetClient,
    TargetCatalog,
)
from orion.integrations.mcp import MCPConfigurationError, MCPManager, load_config
from orion.integrations.ssh.config import load_configuration as load_ssh_configuration
from orion.integrations.ssh.transport import CommandRouter
from orion.knowledge import KnowledgeService, knowledge_registrations
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.local_embeddings import LocalE5Embeddings
from orion.knowledge.ports import Chunker, DocumentParser
from orion.knowledge.semantic import SemanticIndexService
from orion.models.backend import ModelBackend, ModelStreamSettings, ReasoningMode
from orion.models.credential_store import credentials_for_database
from orion.models.providers.factory import default_provider_registry
from orion.models.registry import ProviderRegistry
from orion.observability import ApplicationLog
from orion.paths import database_path as default_database_path
from orion.persistence.ownership import RuntimeLease
from orion.persistence.sqlite import SQLiteStore
from orion.projects import ProjectService
from orion.scheduler.engine import SchedulerEngine
from orion.scheduler.service import SchedulerService
from orion.scheduler.tools import scheduler_registrations
from orion.skills.service import SkillService
from orion.skills.tools import skill_registrations
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
    scheduler: SchedulerService
    scheduler_engine: SchedulerEngine
    endpoints: EndpointManager
    native_auth: NativeAuthService
    requests: RequestService
    endpoint_enabled: bool = False
    mcp: MCPManager | None = None
    mutation_authorization: MutationAuthorizationPolicy | None = None
    model_configurations: ModelConfigurationService | None = None
    commands: CommandService | None = None
    skills: SkillService | None = None


def build_application(
    database_path: Path | None = None,
    backend: ModelBackend | None = None,
    tool_registrations: tuple[ToolRegistration, ...] | None = None,
    internet_client: InternetClient | None = None,
    infrastructure_catalog: TargetCatalog | None = None,
    linux_executor: LinuxExecutor | None = None,
    knowledge_parser: DocumentParser | None = None,
    knowledge_chunker: Chunker | None = None,
    blocked_tool_operation_kinds: frozenset[str] = frozenset(),
    endpoint_enabled: bool | None = None,
    mcp_manager: MCPManager | None = None,
    mcp_registrations: tuple[ToolRegistration, ...] = (),
    seed_model_from_environment: bool = True,
) -> OrionApplication:
    """Build the complete local application with one registry snapshot."""
    if mcp_manager is None and load_config().servers:
        raise MCPConfigurationError("async_lifecycle_required")
    stream_settings = ModelStreamSettings.from_environment()
    infrastructure_config = _infrastructure_configuration()
    resolved_path = database_path or default_database_path()
    ownership = RuntimeLease(resolved_path)
    try:
        store = SQLiteStore(resolved_path, on_close=ownership.close)
    except BaseException:
        ownership.close()
        raise
    try:
        if seed_model_from_environment:
            _configure_model_from_environment(store)
        access = LocalAccessAdapter()
        enabled = (
            endpoint_enabled
            if endpoint_enabled is not None
            else os.getenv("ORION_ENDPOINTS", "0") == "1"
        )
        endpoints = EndpointManager(EndpointStore(store))
        command_transport = CommandRouter(
            endpoints, load_ssh_configuration(), worker_enabled=enabled
        )
        ssh_enabled = bool(command_transport.model_context())
        commands = CommandService(store, command_transport)
        registry_builder = ToolRegistryBuilder()
        skills = SkillService(store)
        for registration in skill_registrations(skills):
            registry_builder.register(registration.definition, registration.handler)
        knowledge = KnowledgeService(
            store,
            LocalBlobStore(resolved_path.parent / "blobs"),
            parser=knowledge_parser,
            chunker=knowledge_chunker,
            semantic_retriever_factory=(lambda: SemanticIndexService(store, LocalE5Embeddings()))
            if os.getenv("ORION_KNOWLEDGE_SEMANTIC_SEARCH", "off") == "hybrid"
            else None,
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
        ):
            registry_builder.register(registration.definition, registration.handler)
        scheduler = SchedulerService(store)
        for registration in scheduler_registrations(scheduler):
            registry_builder.register(registration.definition, registration.handler)
        for registration in mcp_registrations:
            registry_builder.register(registration.definition, registration.handler)
        if enabled:
            for registration in endpoint_registrations(endpoints):
                registry_builder.register(registration.definition, registration.handler)
        if enabled or ssh_enabled:
            for registration in command_registrations(commands):
                registry_builder.register(registration.definition, registration.handler)
        registry = registry_builder.freeze()
        skills.capabilities = frozenset(
            definition.name for definition in registry.definitions()
        ) | (
            frozenset({"mcp-host"})
            if any(definition.name.startswith("mcp.") for definition in registry.definitions())
            else frozenset()
        )
        authorization = MutationAuthorizationPolicy.from_mapping(
            infrastructure_config or {},
            registry.definitions(),
            lambda family, target_ref: (
                _target_is_configured(infrastructure_catalog, family, target_ref)
                if family not in {"endpoint", "system"}
                else command_transport.configured(target_ref)
                if family == "system"
                else enabled and endpoints.configured(target_ref)
            ),
        )
        selected_backend = backend or default_provider_registry(stream_settings)
        diagnostic_sink = (
            BoundedModelInputDiagnostics()
            if os.getenv("ORION_RUNTIME_DIAGNOSTICS") == "qa"
            else None
        )
        configuration_registry = (
            selected_backend
            if isinstance(selected_backend, ProviderRegistry)
            else default_provider_registry(stream_settings, compatible_backend=selected_backend)
        )
        model_configurations = ModelConfigurationService(
            store, configuration_registry, credentials_for_database(resolved_path)
        )
        runtime = ChatRuntime(
            store,
            selected_backend,
            registry,
            access,
            infrastructure_catalog.model_context() + command_transport.model_context(),
            ApplicationLog(Path(os.environ["ORION_LOG_PATH"]))
            if os.getenv("ORION_LOG_PATH")
            else None,
            blocked_tool_operation_kinds,
            diagnostic_sink,
            mutation_authorization=authorization,
            endpoint_summary=lambda target: next(
                (row for row in endpoints.list() if row["endpoint_id"] == target), None
            ),
            settings_provider=model_configurations.active_settings
            if model_configurations
            else None,
            on_request_interrupt=commands.cancel_request,
            skill_request_start=skills.begin_request,
            skill_context=skills.context,
            skill_request_end=skills.end_request,
        )
        store.recover_interrupted_requests(ownership)
        return OrionApplication(
            store=store,
            access=access,
            backend=selected_backend,
            registry=registry,
            knowledge=knowledge,
            projects=projects,
            internet=internet,
            runtime=runtime,
            scheduler=scheduler,
            scheduler_engine=SchedulerEngine(store, runtime, scheduler),
            endpoints=endpoints,
            native_auth=NativeAuthService(store),
            requests=RequestService(store, runtime, access),
            endpoint_enabled=enabled,
            mutation_authorization=authorization,
            mcp=mcp_manager,
            model_configurations=model_configurations,
            commands=commands,
            skills=skills,
        )
    except BaseException:
        store.close()
        raise


def prepare_mcp_manager() -> MCPManager | None:
    """Validate administrative config and resolve secrets before any application state."""
    config = load_config()
    return MCPManager(config) if config.servers else None


@asynccontextmanager
async def application_context(
    database_path: Path | None = None,
    backend: ModelBackend | None = None,
    *,
    application: OrionApplication | None = None,
    mcp_manager: MCPManager | None = None,
) -> AsyncIterator[OrionApplication]:
    """Own async discovery before composition/freeze and close all integration resources."""
    if application is not None:
        yield application
        return
    manager = mcp_manager or prepare_mcp_manager()
    if manager is None:
        local_application = build_application(database_path, backend)
        try:
            yield local_application
        finally:
            await local_application.requests.close()
            if local_application.commands:
                await local_application.commands.close()
            await local_application.endpoints.close()
            local_application.store.close()
        return
    assembled: OrionApplication | None = None
    try:
        registrations = await manager.start()
        try:
            assembled = build_application(
                database_path, backend, mcp_manager=manager, mcp_registrations=registrations
            )
        except ValueError:
            raise MCPConfigurationError("composition") from None
        yield assembled
    finally:
        if assembled is not None:
            await assembled.requests.close()
        await manager.close()
        if assembled is not None:
            if assembled.commands:
                await assembled.commands.close()
            await assembled.endpoints.close()
            assembled.store.close()


def _configure_model_from_environment(store: SQLiteStore) -> None:
    if store.model_configs():
        return
    base_url, model_id = os.getenv("ORION_MODEL_BASE_URL"), os.getenv("ORION_MODEL_ID")
    if base_url and model_id:
        store.create_model_config(
            "openai_compatible",
            base_url,
            model_id,
            None,
            ReasoningMode(os.getenv("ORION_MODEL_REASONING_MODE", "auto")).value,
            credential_ref="env:ORION_MODEL_API_KEY" if os.getenv("ORION_MODEL_API_KEY") else None,
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
