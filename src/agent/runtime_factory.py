from __future__ import annotations

import sys
from typing import Any

from src.agent.conversation_store import ConversationStore
from src.agent.deterministic_agent import DeterministicAgent
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.llm_assessment_adapter import LLMAssessmentAdapter
from src.model.llm_client import LLMClient
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.execution_graph import ExecutionGraphBuilder
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.intent_resolver import IntentResolver
from src.pipeline.security.inspector_chain import InspectorChain
from src.pipeline.security.parameter_safety_inspector import ParameterSafetyInspector
from src.pipeline.security.read_only_inspector import ReadOnlyInspector
from src.pipeline.security.target_inspector import TargetInspector
from src.pipeline.target_resolver import TargetResolver
from src.shared.config import get_config
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
    "knowledge_base": (),
}


def _load_tools_config() -> dict[str, dict[str, Any]]:
    """Load infrastructure tool configuration from OrionConfig.

    Credentials (url, token) are overlaid from config/secrets.local.json
    on top of tools.json. This keeps secrets out of version control.

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
    elif tool_type == "knowledge_base":
        from src.tool.knowledge_base_tool import KnowledgeBaseTool

        return KnowledgeBaseTool()
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
        available = ", ".join(sorted(config.servers))
        raise RuntimeError(
            f"Server {server_name!r} not found. Available servers: {available}"
        )
    cfg = ServerConfig.model_validate(raw)

    base_url: str = cfg.base_url
    api_key: str | None = cfg.api_key
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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def create_deterministic_agent(
    target_store_path: str = "targets.json",
    server_name: str | None = None,
    model: str | None = None,
    assessment_adapter: AssessmentModelAdapter | None = None,
    conversation_store: ConversationStore | None = None,
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

    engine = ExecutionEngine(
        intent_resolver=IntentResolver(),
        target_resolver=TargetResolver(target_registry=registry),
        evidence_planner=EvidencePlanner(),
        capability_resolver=CapabilityResolver(),
        execution_planner=ExecutionPlanner(),
        graph_builder=ExecutionGraphBuilder(),
        knowledge_tool=kt,
        evidence_merge=EvidenceMerge(),
    )

    if assessment_adapter is None:
        server_name = server_name or "sv1"
        model = model or None
        base_url = "unknown"
        resolved_model = "unknown"
        try:
            cfg = get_config().servers.get(server_name, {})
            base_url = str(cfg.get("base_url", "unknown"))
            resolved_model = str(cfg.get("model", "unknown"))
        except Exception:
            _warn(f"failed to load server config for '{server_name}', using defaults")
        _info(
            "llm",
            provider=base_url,
            model=resolved_model,
            message="Initializing LLM adapter",
        )
        assessment_adapter = _build_assessment_adapter(
            server_name=server_name,
            model=model,
        )

    agent = DeterministicAgent(
        execution_engine=engine,
        assessment_model=assessment_adapter,
        conversation_store=conversation_store,
    )
    _info("orion", message="orion started")
    return agent
