"""Production composition root for the canonical Orion agent runtime.

This module constructs configured model and tool resources, then hands them to
the canonical composition root. It contains no semantic routing, prose parsing,
target inference, capability selection, or execution authority.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.agent.composition import (
    CanonicalAgentComponents,
    build_canonical_agent_components,
)
from src.agent.permissions import PermissionMode
from src.agent.runtime import AgentRuntime, AgentRuntimeConfig
from src.agent.session_agent import CanonicalSessionAgent
from src.model.agent_backend import (
    AgentModelBackend,
    FallbackAgentBackend,
    UnconfiguredAgentBackend,
)
from src.model.agent_provider_bridge import AgentBackendProvider
from src.model.agent_llm_adapter import AgentLLMAdapter
from src.model.llm_client import LLMClient
from src.model.config_store import FeatureFlagStore
from src.pipeline.external_verification import ExternalVerificationExecutor
from src.pipeline.security.inspector_chain import InspectorChain
from src.pipeline.security.parameter_safety_inspector import (
    ParameterSafetyInspector,
)
from src.pipeline.security.read_only_inspector import ReadOnlyInspector
from src.pipeline.security.target_inspector import TargetInspector
from src.shared.config import OrionConfig, get_config
from src.shared.config_errors import InvalidConfigValueError
from src.shared.config_schema import ServerConfig
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.registry import ToolRegistry
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore


@dataclass(frozen=True, slots=True)
class CanonicalProductionRuntime:
    """Configured resources belonging to one canonical runtime instance."""

    components: CanonicalAgentComponents
    target_registry: TargetRegistry
    knowledge_tool: KnowledgeTool
    model_backend: AgentModelBackend
    model_backends: tuple[AgentModelBackend, ...]
    providers: tuple[AgentBackendProvider, ...]
    external_verification: ExternalVerificationExecutor

    @property
    def runtime(self) -> AgentRuntime:
        return self.components.runtime


_AUTO_TOOL_REGISTRY = ToolRegistry()

_SUPPORTED_TOOL_TYPES: dict[str, tuple[str, ...]] = {}

_FALLBACK_TOOL_TYPES: dict[str, tuple[str, ...]] = {
    "zabbix": ("url", "token"),
    "grafana": ("url", "token"),
    "internet": (),
}


def _warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def _populate_supported_tool_types() -> dict[str, tuple[str, ...]]:
    discovered = _AUTO_TOOL_REGISTRY.discover_required_fields()
    if discovered:
        return discovered
    return dict(_FALLBACK_TOOL_TYPES)


def _build_auto_tool(
    tool_type: str,
    cfg: Mapping[str, Any],
):
    discovered = _AUTO_TOOL_REGISTRY.discover_classes()
    tool_cls = discovered.get(tool_type)

    if tool_cls is not None:
        required = _SUPPORTED_TOOL_TYPES.get(
            tool_type,
            (),
        )
        kwargs: dict[str, Any] = {}

        for field in required:
            if field in cfg:
                kwargs[field] = cfg[field]

        for key, value in cfg.items():
            if (
                key not in {"tool", "target"}
                and key not in kwargs
                and isinstance(
                    value,
                    (str, int, float),
                )
            ):
                kwargs[key] = value

        try:
            return tool_cls(**kwargs)
        except TypeError:
            return tool_cls()
        except Exception:
            return None

    if tool_type == "zabbix":
        from src.tool.zabbix_tool import ZabbixTool

        return ZabbixTool(
            url=str(cfg.get("url", "")),
            token=str(cfg.get("token", "")),
            timeout=int(cfg.get("timeout", 10)),
        )

    if tool_type == "grafana":
        from src.tool.grafana_tool import GrafanaTool

        return GrafanaTool(
            url=str(cfg.get("url", "")),
            token=str(cfg.get("token", "")),
            timeout=int(cfg.get("timeout", 10)),
        )

    if tool_type == "internet":
        from src.tool.internet_tool import InternetTool

        return InternetTool()

    return None


def _register_single_tool(
    registry: TargetRegistry,
    entry_name: str,
    cfg: Mapping[str, Any],
) -> None:
    tool_type = cfg.get("tool")

    if not isinstance(tool_type, str) or not tool_type:
        _warn(
            f"tools.json entry {entry_name!r} is missing "
            "a valid 'tool' field. Skipping."
        )
        return

    global _SUPPORTED_TOOL_TYPES

    if not _SUPPORTED_TOOL_TYPES:
        _SUPPORTED_TOOL_TYPES = (
            _populate_supported_tool_types()
        )

    if tool_type not in _SUPPORTED_TOOL_TYPES:
        supported = ", ".join(
            sorted(_SUPPORTED_TOOL_TYPES)
        )
        _warn(
            f"Unknown tool type {tool_type!r} in "
            f"tools.json entry {entry_name!r}. "
            f"Supported types: {supported}. Skipping."
        )
        return

    required = _SUPPORTED_TOOL_TYPES[tool_type]
    missing = [
        field
        for field in required
        if not cfg.get(field)
    ]

    if missing:
        _warn(
            f"tools.json entry {entry_name!r} of type "
            f"{tool_type!r} is missing required fields: "
            f"{', '.join(missing)}. Skipping."
        )
        return

    target_name = str(
        cfg.get("target", entry_name)
    )

    tool = _build_auto_tool(
        tool_type,
        cfg,
    )

    if tool is None:
        _warn(
            f"Failed to construct tool {tool_type!r} "
            f"from tools.json entry {entry_name!r}. "
            "Skipping."
        )
        return

    try:
        registry.register_tool(
            name=target_name,
            tool=tool,
        )
    except ValueError as exc:
        _warn(
            f"Failed to register tool "
            f"{target_name!r}: {exc}"
        )


def _register_tools(
    registry: TargetRegistry,
    tools: Mapping[str, object],
) -> None:
    for entry_name, raw in tools.items():
        if not isinstance(raw, Mapping):
            _warn(
                f"tools.json entry {entry_name!r} "
                "is not an object. Skipping."
            )
            continue

        _register_single_tool(
            registry,
            entry_name,
            raw,
        )


def _normalize_api_key(
    value: object,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()

    if (
        not normalized
        or normalized.upper() == "EMPTY"
    ):
        return None

    return normalized


def _build_openai_compatible_backend(
    cfg: ServerConfig,
    *,
    model_override: str | None,
) -> AgentModelBackend:
    provider = (
        cfg.provider or "openai"
    ).strip().casefold()

    client = LLMClient(
        base_url=cfg.base_url,
        model=model_override or cfg.model,
        api_key=_normalize_api_key(
            cfg.api_key
        ),
        timeout=cfg.timeout,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        supports_structured_output=(
            False
            if provider == "ollama"
            else None
        ),
    )

    return AgentLLMAdapter(
        client=client
    )


def _build_server_backend(
    raw: Mapping[str, object],
    *,
    model_override: str | None,
) -> AgentModelBackend:
    cfg = ServerConfig.model_validate(
        dict(raw)
    )

    provider = (
        cfg.provider or "openai"
    ).strip().casefold()

    if provider != "anthropic":
        return _build_openai_compatible_backend(
            cfg,
            model_override=model_override,
        )

    try:
        from src.model.providers.anthropic_agent_adapter import (
            AnthropicAgentAdapter,
        )
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package is required for "
            "an Anthropic model provider."
        ) from exc

    api_key = _normalize_api_key(
        cfg.api_key
    )

    if api_key is None:
        _warn(
            "Anthropic provider has no api_key; "
            "provider calls will fail."
        )

    return AnthropicAgentAdapter(
        api_key=api_key or "",
        model=model_override or cfg.model,
        timeout=cfg.timeout,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )


def _configured_model_backends(
    config: OrionConfig,
    *,
    server_name: str | None,
    model: str | None,
) -> tuple[AgentModelBackend, ...]:
    if not config.servers:
        return (
            UnconfiguredAgentBackend(),
        )

    primary_name = (
        server_name
        or config.active_server_name
    )

    if not primary_name:
        primary_name = next(
            iter(sorted(config.servers))
        )

    if primary_name not in config.servers:
        available = ", ".join(
            sorted(config.servers)
        )

        raise InvalidConfigValueError(
            file="servers.json",
            key=primary_name,
            expected="valid server entry",
            received=(
                "not found. Available servers: "
                f"{available}"
            ),
        )

    ordered_names = [primary_name]

    for name in config.fallback_chain:
        if (
            name in config.servers
            and name not in ordered_names
        ):
            ordered_names.append(name)

    return tuple(
        _build_server_backend(
            config.servers[name],
            model_override=model,
        )
        for name in ordered_names
    )


def _flatten_model_backend(
    backend: AgentModelBackend,
) -> tuple[AgentModelBackend, ...]:
    if not isinstance(
        backend,
        AgentModelBackend,
    ):
        raise TypeError(
            "model_backend must be "
            "AgentModelBackend."
        )

    nested = getattr(
        backend,
        "backends",
        None,
    )

    if (
        isinstance(nested, Sequence)
        and not isinstance(
            nested,
            (str, bytes),
        )
        and nested
    ):
        result = tuple(nested)

        if not all(
            isinstance(
                item,
                AgentModelBackend,
            )
            for item in result
        ):
            raise TypeError(
                "assessment backend chain contains "
                "an invalid backend."
            )

        return result

    return (backend,)


def _model_backend_chain(
    backends: tuple[
        AgentModelBackend,
        ...,
    ],
) -> AgentModelBackend:
    if not backends:
        raise ValueError(
            "At least one assessment backend "
            "is required."
        )

    if len(backends) == 1:
        return backends[0]

    return FallbackAgentBackend(
        backends
    )


def _build_target_registry(
    *,
    target_store_path: str,
    config: OrionConfig,
) -> TargetRegistry:
    store = TargetStore(
        path=target_store_path,
        discover_ssh_targets_enabled=True,
    )

    registry = TargetRegistry(
        store=store
    )

    _register_tools(
        registry,
        config.tools,
    )

    return registry


def _build_knowledge_tool(
    registry: TargetRegistry,
) -> KnowledgeTool:
    target_inspector = TargetInspector()

    inspectors = InspectorChain()
    inspectors.add(ReadOnlyInspector())
    inspectors.add(
        ParameterSafetyInspector()
    )
    inspectors.add(target_inspector)

    for target_name in registry.target_names():
        target_inspector.add_safe_target(
            target_name
        )

    return KnowledgeTool(
        target_registry=registry,
        inspector_chain=inspectors,
    )


def create_canonical_production_runtime(
    *,
    target_store_path: str = "targets.json",
    server_name: str | None = None,
    model: str | None = None,
    model_backend: (
        AgentModelBackend | None
    ) = None,
    config: OrionConfig | None = None,
    model_timeout_seconds: float = 30.0,
    runtime_config: (
        AgentRuntimeConfig | None
    ) = None,
) -> CanonicalProductionRuntime:
    """Build one fully configured canonical runtime.

    Model providers propose decisions. The canonical harness owns
    capabilities, exact references, permissions, execution, evidence,
    budgets, and completion.
    """

    resolved_config = (
        config
        if config is not None
        else get_config()
    )

    if not isinstance(
        resolved_config,
        OrionConfig,
    ):
        raise TypeError(
            "config must be OrionConfig "
            "or None."
        )

    target_registry = (
        _build_target_registry(
            target_store_path=(
                target_store_path
            ),
            config=resolved_config,
        )
    )

    knowledge_tool = (
        _build_knowledge_tool(
            target_registry
        )
    )

    if model_backend is None:
        backends = (
            _configured_model_backends(
                resolved_config,
                server_name=server_name,
                model=model,
            )
        )
    else:
        backends = (
            _flatten_model_backend(
                model_backend
            )
        )

    model_backend = (
        _model_backend_chain(backends)
    )

    flags = FeatureFlagStore().load()

    external_verification = (
        ExternalVerificationExecutor(
            knowledge_tool,
            enabled=(
                flags.external_verification_v1
                and flags.web_search_v1
            ),
        )
    )

    providers = tuple(
        AgentBackendProvider(backend)
        for backend in backends
        if not isinstance(
            backend,
            UnconfiguredAgentBackend,
        )
    )

    components = (
        build_canonical_agent_components(
            knowledge_tool=knowledge_tool,
            target_registry=target_registry,
            providers=providers,
            model_timeout_seconds=(
                model_timeout_seconds
            ),
            runtime_config=runtime_config,
            external_verification=(
                external_verification
            ),
        )
    )

    return CanonicalProductionRuntime(
        components=components,
        target_registry=target_registry,
        knowledge_tool=knowledge_tool,
        model_backend=(
            model_backend
        ),
        model_backends=backends,
        providers=providers,
        external_verification=(
            external_verification
        ),
    )


def create_canonical_session_agent(
    *,
    target_store_path: str = "targets.json",
    server_name: str | None = None,
    model: str | None = None,
    model_backend: (
        AgentModelBackend | None
    ) = None,
    conversation_store: object | None = None,
    config: OrionConfig | None = None,
    model_timeout_seconds: float = 30.0,
    runtime_config: (
        AgentRuntimeConfig | None
    ) = None,
    permission_mode: (
        PermissionMode
    ) = PermissionMode.READ,
) -> CanonicalSessionAgent:
    """Build one session-local canonical public agent."""

    bundle = (
        create_canonical_production_runtime(
            target_store_path=target_store_path,
            server_name=server_name,
            model=model,
            model_backend=(
                model_backend
            ),
            config=config,
            model_timeout_seconds=(
                model_timeout_seconds
            ),
            runtime_config=runtime_config,
        )
    )

    return CanonicalSessionAgent(
        runtime=bundle.runtime,
        model_backend=(
            bundle.model_backend
        ),
        conversation_store=(
            conversation_store
        ),
        permission_mode=permission_mode,
    )


__all__ = [
    "CanonicalProductionRuntime",
    "create_canonical_production_runtime",
    "create_canonical_session_agent",
]
