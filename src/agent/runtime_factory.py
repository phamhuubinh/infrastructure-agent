from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from src.agent.conversation_store import ConversationStoreProtocol
from src.agent.deterministic_agent import DeterministicAgent
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.assessment_planner_provider import (
    AssessmentPlannerProvider,
    UnconfiguredPlannerProvider,
)
from src.model.llm_assessment_adapter import LLMAssessmentAdapter
from src.model.llm_client import LLMClient
from src.model.semantic_planner_adapter import SemanticPlannerAdapter
from src.model.unconfigured_adapter import UnconfiguredAssessmentAdapter

if TYPE_CHECKING:
    from src.model.providers.registry import ProviderRegistry

from src.model.config_store import FeatureFlagStore
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.evidence_cache import EvidenceCache
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.execution_graph import ExecutionGraphBuilder
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.external_verification import ExternalVerificationExecutor
from src.pipeline.intent_resolver import IntentResolver
from src.pipeline.security.inspector_chain import InspectorChain
from src.pipeline.security.parameter_safety_inspector import ParameterSafetyInspector
from src.pipeline.security.read_only_inspector import ReadOnlyInspector
from src.pipeline.security.target_inspector import TargetInspector
from src.pipeline.target_resolver import TargetResolver
from src.shared.config import get_config
from src.shared.config_errors import InvalidConfigValueError
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore

# ---------------------------------------------------------------------------
# Model server configuration (servers.json) — via OrionConfig
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Diagnostics — single warning helper
# ---------------------------------------------------------------------------
# All Runtime Configuration warnings go through _warn().
# There is exactly one stderr print site in the entire runtime factory.


def _warn(message: str) -> None:
    """Emit a runtime configuration warning to stderr.

    Using a single helper ensures consistent diagnostic output and
    makes warning behavior testable.
    """
    print(f"Warning: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Infrastructure tool configuration (tools.json) — via OrionConfig
# ---------------------------------------------------------------------------
from src.tool.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Auto-discovered tool registry (replaces hardcoded _SUPPORTED_TOOL_TYPES)
# ---------------------------------------------------------------------------

_AUTO_TOOL_REGISTRY = ToolRegistry()

_SUPPORTED_TOOL_TYPES: dict[str, tuple[str, ...]] = {}

# Fallback types used if auto-discovery returns empty (e.g. import errors).
_FALLBACK_TOOL_TYPES: dict[str, tuple[str, ...]] = {
    "zabbix": ("url", "token"),
    "grafana": ("url", "token"),
    "internet": (),
}


def _load_tools_config() -> dict[str, dict[str, Any]]:
    """Load infrastructure tool configuration from OrionConfig.

    Credentials (url, token) are overlaid from the external credentials file
    on top of tools.json. This keeps secrets outside the project and image.

    Returns an empty dict if tools.json does not exist.
    Warnings are emitted via _warn() for invalid entries.
    """
    config = get_config()
    return config.tools


def _build_auto_tool(tool_type: str, cfg: dict[str, Any]):
    """Auto-construct a tool using the discovered class.

    Falls back to hardcoded construction if the tool class is not found
    in the auto-discovered registry.
    """
    discovered = _AUTO_TOOL_REGISTRY.discover_classes()
    tool_cls = discovered.get(tool_type)

    if tool_cls is not None:
        # Build using the discovered class constructor signature
        required = _SUPPORTED_TOOL_TYPES.get(tool_type, ())
        kwargs: dict[str, Any] = {}
        for field in required:
            if field in cfg:
                kwargs[field] = cfg[field]
        # Add optional fields present in cfg
        for key, val in cfg.items():
            if (
                key not in ("tool", "target")
                and key not in kwargs
                and isinstance(val, (str, int, float))
            ):
                kwargs[key] = val
        try:
            return tool_cls(**kwargs)
        except TypeError:
            # Fall back to position- or dict-style construction
            return tool_cls()
        except Exception:
            return None

    # Hardcoded fallback for backward compatibility
    if tool_type == "zabbix":
        from src.tool.zabbix_tool import ZabbixTool

        return ZabbixTool(
            url=str(cfg.get("url", "")),
            token=str(cfg.get("token", "")),
            timeout=int(cfg.get("timeout", 10)),
        )
    elif tool_type == "grafana":
        from src.tool.grafana_tool import GrafanaTool

        return GrafanaTool(
            url=str(cfg.get("url", "")),
            token=str(cfg.get("token", "")),
            timeout=int(cfg.get("timeout", 10)),
        )
    elif tool_type == "internet":
        from src.tool.internet_tool import InternetTool

        return InternetTool()
    return None


def _register_single_tool(
    registry: TargetRegistry,
    entry_name: str,
    cfg: dict[str, Any],
) -> None:
    """Register one tool from a tools.json entry.

    Validates the entry, constructs the tool (via auto-discovery or
    fallback), and registers it.  Warnings are emitted via _warn()
    for invalid entries instead of crashing.
    """
    tool_type = cfg.get("tool")
    if not isinstance(tool_type, str) or not tool_type:
        _warn(
            f"tools.json entry '{entry_name}' is missing "
            f"a valid 'tool' field. Skipping."
        )
        return

    if tool_type not in _SUPPORTED_TOOL_TYPES:
        supported = ", ".join(sorted(_SUPPORTED_TOOL_TYPES))
        _warn(
            f"Unknown tool type '{tool_type}' in "
            f"tools.json entry '{entry_name}'. "
            f"Supported types: {supported}. Skipping."
        )
        return

    required_fields = _SUPPORTED_TOOL_TYPES[tool_type]
    missing = [f for f in required_fields if not cfg.get(f)]
    if missing:
        _warn(
            f"tools.json entry '{entry_name}' of type "
            f"'{tool_type}' is missing required fields: "
            f"{', '.join(missing)}. Skipping."
        )
        return

    target_name = str(cfg.get("target", entry_name))

    tool = _build_auto_tool(tool_type, cfg)
    if tool is None:
        _warn(
            f"Failed to construct tool '{tool_type}' from "
            f"tools.json entry '{entry_name}'. Skipping."
        )
        return

    try:
        registry.register_tool(name=target_name, tool=tool)
    except ValueError as exc:
        _warn(
            f"Failed to register tool '{target_name}' "
            f"from tools.json entry '{entry_name}': {exc}"
        )


def _populate_supported_tool_types() -> dict[str, tuple[str, ...]]:
    """Build _SUPPORTED_TOOL_TYPES from auto-discovery.

    Returns the populated dict.  Falls back to _FALLBACK_TOOL_TYPES if
    auto-discovery returns no results.
    """
    discovered = _AUTO_TOOL_REGISTRY.discover_required_fields()
    if discovered:
        return discovered
    # Auto-discovery returned empty — use hardcoded fallback.
    return dict(_FALLBACK_TOOL_TYPES)


def _register_tools(
    registry: TargetRegistry,
    tools_config: dict[str, dict[str, Any]],
) -> None:
    """Register all tools from tools.json into the TargetRegistry.

    Each entry is validated and registered independently.
    A single invalid entry does not block other entries.
    """
    # Populate _SUPPORTED_TOOL_TYPES from auto-discovery on first call.
    global _SUPPORTED_TOOL_TYPES
    if not _SUPPORTED_TOOL_TYPES:
        _SUPPORTED_TOOL_TYPES = _populate_supported_tool_types()

    for entry_name, cfg in tools_config.items():
        if not isinstance(cfg, dict):
            _warn(f"tools.json entry '{entry_name}' is not a JSON object. Skipping.")
            continue
        _register_single_tool(registry, entry_name, cfg)


# ---------------------------------------------------------------------------
# Assessment adapter construction
# ---------------------------------------------------------------------------


def _normalize_api_key(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return None if not normalized or normalized.upper() == "EMPTY" else normalized


def _build_assessment_adapter(
    server_name: str | None = None,
    model: str | None = None,
) -> AssessmentModelAdapter:
    from src.shared.config_schema import ServerConfig

    config = get_config()
    if server_name is None:
        server_name = config.active_server_name or "sv1"
    raw = config.servers.get(server_name)
    if raw is None:
        available = ", ".join(sorted(config.servers)) or "(none)"
        raise InvalidConfigValueError(
            file="servers.json",
            key=server_name,
            expected="valid server entry",
            received=f"not found. Available servers: {available}",
        )
    cfg = ServerConfig.model_validate(raw)

    base_url: str = cfg.base_url
    api_key = _normalize_api_key(cfg.api_key)
    resolved_model: str = model or cfg.model

    client = LLMClient(
        base_url=base_url,
        model=resolved_model,
        api_key=api_key,
        timeout=cfg.timeout,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )

    return LLMAssessmentAdapter(client=client)


def _build_openai_adapter(
    cfg: object,
    model_override: str | None = None,
) -> LLMAssessmentAdapter:
    """Build an LLMAssessmentAdapter from a ServerConfig-like object."""

    def value(name: str, default: Any) -> Any:
        return (
            cfg.get(name, default)
            if isinstance(cfg, dict)
            else getattr(cfg, name, default)
        )

    base_url = str(value("base_url", "http://localhost:8000"))
    api_key = _normalize_api_key(value("api_key", None))
    model = model_override or str(value("model", "gpt-4"))
    timeout = int(value("timeout", 60))
    temperature = float(value("temperature", 0.0))
    max_tokens = int(value("max_tokens", 2048))

    client = LLMClient(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return LLMAssessmentAdapter(client=client)


def _build_anthropic_adapter(
    cfg: object,
    model_override: str | None = None,
) -> AssessmentModelAdapter:
    """Build an AnthropicAssessmentAdapter from a ServerConfig-like object.

    Returns LLMAssessmentAdapter as fallback if anthropic is not installed.
    """

    def value(name: str, default: Any) -> Any:
        return (
            cfg.get(name, default)
            if isinstance(cfg, dict)
            else getattr(cfg, name, default)
        )

    api_key = _normalize_api_key(value("api_key", None))
    model = model_override or str(value("model", "claude-3-haiku-20240307"))
    timeout = int(value("timeout", 180))
    temperature = float(value("temperature", 0.0))
    max_tokens = int(value("max_tokens", 4096))

    if not api_key:
        _warn(
            f"Anthropic provider '{value('base_url', 'unknown')}' "
            f"has no api_key set. Adapter will fail at runtime."
        )

    try:
        from src.model.providers.anthropic_adapter import AnthropicAssessmentAdapter

        return AnthropicAssessmentAdapter(
            api_key=api_key or "",
            model=model,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except ImportError:
        _warn("anthropic package not installed. Install with: pip install anthropic")
        # Return an OpenAI adapter as fallback — it will fail at
        # health_check time and get skipped in the fallback chain.
        return _build_openai_adapter(cfg, model_override=model)


def _build_provider_registry(
    server_name: str | None = None,
    model: str | None = None,
) -> tuple[ProviderRegistry, AssessmentModelAdapter]:
    """Build a ProviderRegistry from all servers in servers.json.

    Creates adapters for every server based on its provider type,
    registers them, and configures the fallback chain.

    Returns:
        (registry, primary_adapter) — the primary adapter is the one
        matching the active server (or server_name override).
    """
    from src.model.providers.registry import ProviderRegistry

    config = get_config()
    registry = ProviderRegistry()
    primary_name = server_name or config.active_server_name or "sv1"
    primary_adapter: AssessmentModelAdapter | None = None

    for srv_name, raw in config.servers.items():
        provider_type = str(raw.get("provider", "openai")).lower()
        adapter: AssessmentModelAdapter

        if provider_type == "anthropic":
            adapter = _build_anthropic_adapter(raw, model_override=model)
        else:
            # openai, ollama, vllm, or unspecified — all use OpenAI-compatible API
            adapter = _build_openai_adapter(raw, model_override=model)

        registry.register(srv_name, adapter)
        if srv_name == primary_name:
            primary_adapter = adapter

    # Configure fallback chain from servers.json.
    registry.fallback_chain = [
        n for n in config.fallback_chain if n in registry.providers
    ]

    # Configure credential pool if present.
    pool_raw = config.credential_pool
    if pool_raw:
        from src.model.providers.credential_pool import CredentialPool

        all_keys: list[str] = []
        for keys in pool_raw.values():
            for k in keys:
                all_keys.append(k)
        if all_keys:
            registry.credential_pool = CredentialPool(keys=all_keys)

    if primary_adapter is None:
        # Primary server not found — use first available.
        if registry.providers:
            primary_adapter = next(iter(registry.providers.values()))
        else:
            raise InvalidConfigValueError(
                file="servers.json",
                key="(all)",
                expected="at least one LLM provider",
                received="no LLM providers configured",
            )

    return registry, primary_adapter


def _build_semantic_planner(
    assessment_adapter: AssessmentModelAdapter,
) -> SemanticPlannerAdapter:
    """Build one session-local semantic planner from the selected model chain."""

    if isinstance(assessment_adapter, UnconfiguredAssessmentAdapter):
        return SemanticPlannerAdapter((UnconfiguredPlannerProvider(),))

    nested = getattr(assessment_adapter, "adapters", None)
    models = (
        tuple(nested)
        if isinstance(nested, list) and nested
        else (assessment_adapter,)
    )
    return SemanticPlannerAdapter(
        tuple(AssessmentPlannerProvider(model) for model in models)
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def create_deterministic_agent(
    target_store_path: str = "targets.json",
    server_name: str | None = None,
    model: str | None = None,
    assessment_adapter: AssessmentModelAdapter | None = None,
    conversation_store: ConversationStoreProtocol | None = None,
) -> DeterministicAgent:
    """Build the production deterministic runtime.

    This is the single Composition Root for the deterministic pipeline.
    All entry points (CLI, benchmark, test) construct the runtime here.

    Infrastructure tools (Zabbix, Grafana, etc.) are configured via
    tools.json — credentials never appear in source code.

    Args:
        target_store_path: Path to the targets configuration file.
        server_name: Name of the model server from servers.json.
        model: Override model name (overrides servers.json model).
        assessment_adapter: Optional pre-built assessment adapter.
                           If None, builds one from server_name/model.

    Returns:
        A fully wired DeterministicAgent ready for execution.
    """
    from src.shared.logger import info as _info

    _info(
        "orion",
        message="orion building",
        target_store=target_store_path,
        server=server_name or "mock",
        model_override=model or "none",
    )
    store = TargetStore(path=target_store_path)

    try:
        registry = TargetRegistry(store=store)
        registry_count = len(registry.target_names())
    except Exception as exc:
        _info(
            "registry",
            status="error",
            error=str(exc)[:120],
            message="Failed to create TargetRegistry, aborting startup",
        )
        raise
    _info("registry", targets=registry_count, message="Target registry loaded")

    # Register infrastructure tools from tools.json (not from hardcoded code).
    tools_config = _load_tools_config()
    _register_tools(registry, tools_config)
    _info(
        "tools",
        tools=len(tools_config),
        message="Tools registered",
    )

    # Build the security inspector chain.
    target_inspector = TargetInspector()
    inspector_chain = InspectorChain()
    inspector_chain.add(ReadOnlyInspector())
    inspector_chain.add(ParameterSafetyInspector())
    inspector_chain.add(target_inspector)

    # Register known targets from the registry as safe targets.
    for target_name in registry.target_names():
        target_inspector.add_safe_target(target_name)

    kt = KnowledgeTool(target_registry=registry, inspector_chain=inspector_chain)

    feature_flags = FeatureFlagStore().load()
    evidence_cache = EvidenceCache()
    engine = ExecutionEngine(
        intent_resolver=IntentResolver(),
        target_resolver=TargetResolver(target_registry=registry),
        evidence_planner=EvidencePlanner(),
        capability_resolver=CapabilityResolver(),
        execution_planner=ExecutionPlanner(),
        graph_builder=ExecutionGraphBuilder(),
        knowledge_tool=kt,
        evidence_merge=EvidenceMerge(
            canonical_facts=feature_flags.canonical_facts,
            structured_command_result=feature_flags.structured_command_result,
        ),
        evidence_cache=evidence_cache,
        feature_flags=feature_flags,
        source_constraints_enabled=feature_flags.source_constraints_v1,
    )

    if assessment_adapter is None:
        model_config = get_config()
        if not model_config.servers:
            assessment_adapter = UnconfiguredAssessmentAdapter()
            _warn("no model configured; Orion will start in setup mode")
        else:
            server_name = server_name or model_config.active_server_name
            model = model or None
            cfg = model_config.servers.get(server_name, {})
            _info(
                "llm",
                provider=str(cfg.get("base_url", "unknown")),
                model=str(cfg.get("model", "unknown")),
                message="Initializing LLM adapter",
            )
            provider_registry, primary_adapter = _build_provider_registry(
                server_name=server_name,
                model=model,
            )
            ordered_adapters = [primary_adapter]
            for provider_name in provider_registry.fallback_chain:
                adapter = provider_registry.providers.get(provider_name)
                if adapter is not None and adapter not in ordered_adapters:
                    ordered_adapters.append(adapter)
            if len(ordered_adapters) > 1:
                from src.model.providers.fallback_adapter import (
                    FallbackAssessmentAdapter,
                )

                assessment_adapter = FallbackAssessmentAdapter(ordered_adapters)
            else:
                assessment_adapter = primary_adapter

    assert assessment_adapter is not None
    semantic_planner = _build_semantic_planner(assessment_adapter)

    agent = DeterministicAgent(
        execution_engine=engine,
        assessment_model=assessment_adapter,
        conversation_store=conversation_store,
        evidence_cache=evidence_cache,
        claim_guard_enabled=feature_flags.claim_guard,
        external_verifier=ExternalVerificationExecutor(
            kt,
            enabled=(
                feature_flags.external_verification_v1
                and feature_flags.web_search_v1
            ),
        ),
        general_agent_routing_enabled=feature_flags.general_agent_routing_v1,
        semantic_planner=semantic_planner,
    )
    _info("orion", message="orion started")
    return agent
