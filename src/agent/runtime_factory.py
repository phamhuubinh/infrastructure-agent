from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from src.shared.logger import info
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
from src.pipeline.target_resolver import TargetResolver
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore


# ---------------------------------------------------------------------------
# Model server configuration (servers.json)
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent

def _load_server_config(
    server_name: str | None = None,
) -> dict[str, object]:
    config_path = _project_root() / "servers.json"
    if not config_path.exists():
        raise RuntimeError(
            "servers.json not found at " + str(config_path) + ". "
            "Create a servers.json with model configuration."
        )
    data = json.loads(config_path.read_text())
    servers: dict[str, object] = data.get("servers", {})
    if server_name is None:
        server_name = data.get("active_server", "")
    cfg = servers.get(server_name)
    if cfg is None:
        available = ", ".join(sorted(servers))
        raise RuntimeError(
            f"Server {server_name!r} not found. "
            f"Available servers: {available}"
        )
    return dict(cfg)


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
# Infrastructure tool configuration (tools.json)
# ---------------------------------------------------------------------------
# Supported tool types and their required config fields.
# Adding a new tool type requires:
#   1. An entry in _SUPPORTED_TOOL_TYPES
#   2. An import and construction block in _register_single_tool

from src.shared.secrets import load_secrets

_SUPPORTED_TOOL_TYPES: dict[str, tuple[str, ...]] = {
    "zabbix": ("url", "token"),
    "grafana": ("url", "token"),
}


def _load_tools_config() -> dict[str, dict[str, Any]]:
    """Load infrastructure tool configuration from tools.json and secrets.

    Credentials (url, token) are overlaid from config/secrets.local.json
    on top of tools.json. This keeps secrets out of version control.

    Returns an empty dict if tools.json does not exist.
    Warnings are emitted via _warn() for invalid JSON or read errors.
    """
    config_path = _project_root() / "tools.json"
    if not config_path.exists():
        return {}
    try:
        raw = config_path.read_text()
        data = json.loads(raw)
        if not isinstance(data, dict):
            _warn(
                "tools.json must contain a JSON object at top level. "
                "Skipping tool registration."
            )
            return {}

        config: dict[str, dict[str, Any]] = dict(data)

        # Overlay secrets from config/secrets.local.json
        try:
            secrets = load_secrets()
            for tool_name, secret_cfg in secrets.items():
                if tool_name in config:
                    config[tool_name].update(secret_cfg)
        except FileNotFoundError:
            pass  # secrets file is optional for tools that don't need it

        return config
    except json.JSONDecodeError as exc:
        _warn(
            f"tools.json contains invalid JSON ({exc}). "
            f"Skipping tool registration."
        )
        return {}
    except OSError as exc:
        _warn(
            f"Cannot read tools.json ({exc}). "
            f"Skipping tool registration."
        )
        return {}


def _register_single_tool(
    registry: TargetRegistry,
    entry_name: str,
    cfg: dict[str, Any],
) -> None:
    """Register one tool from a tools.json entry.

    Validates the entry, constructs the tool, and registers it.
    Warnings are emitted via _warn() for invalid entries instead of crashing.
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

    if tool_type == "zabbix":
        from src.tool.zabbix_tool import ZabbixTool

        tool = ZabbixTool(
            url=str(cfg["url"]),
            token=str(cfg["token"]),
            timeout=int(cfg.get("timeout", 10)),
        )
    elif tool_type == "grafana":
        from src.tool.grafana_tool import GrafanaTool

        tool = GrafanaTool(
            url=str(cfg["url"]),
            token=str(cfg["token"]),
            timeout=int(cfg.get("timeout", 10)),
        )
    else:
        return  # pragma: no cover — unreachable via _SUPPORTED_TOOL_TYPES check

    try:
        registry.register_tool(name=target_name, tool=tool)
    except ValueError as exc:
        _warn(
            f"Failed to register tool '{target_name}' "
            f"from tools.json entry '{entry_name}': {exc}"
        )


def _register_tools(
    registry: TargetRegistry,
    tools_config: dict[str, dict[str, Any]],
) -> None:
    """Register all tools from tools.json into the TargetRegistry.

    Each entry is validated and registered independently.
    A single invalid entry does not block other entries.
    """
    for entry_name, cfg in tools_config.items():
        if not isinstance(cfg, dict):
            _warn(
                f"tools.json entry '{entry_name}' is not a JSON object. "
                f"Skipping."
            )
            continue
        _register_single_tool(registry, entry_name, cfg)


# ---------------------------------------------------------------------------
# Assessment adapter construction
# ---------------------------------------------------------------------------

def _build_assessment_adapter(
    server_name: str | None = None,
    model: str | None = None,
) -> AssessmentModelAdapter:
    config = _load_server_config(server_name)

    base_url: str = str(config.get("base_url", "http://localhost:8000"))
    api_key: str | None = config.get("api_key")
    resolved_model: str = model or str(config.get("model", "gpt-4"))

    client = LLMClient(
        base_url=base_url,
        model=resolved_model,
        api_key=api_key,
        timeout=int(config.get("timeout", 60)),
        temperature=float(config.get("temperature", 0.0)),
        max_tokens=int(config.get("max_tokens", 2048)),
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
    _info("orion", message="orion building", target_store=target_store_path, server=server_name or "mock", model_override=model or "none")
    store = TargetStore(path=target_store_path)

    registry_count = 0
    try:
        registry = TargetRegistry(store=store)
        registry_count = len(registry.target_names())
    except Exception:
        registry = TargetRegistry(store=store)
    _info("registry", targets=registry_count, message="Target registry loaded")

    # Register infrastructure tools from tools.json (not from hardcoded code).
    tools_config = _load_tools_config()
    _register_tools(registry, tools_config)
    _info("tools", tools=len(tools_config.get("tools", [])) if isinstance(tools_config, dict) else 0, message="Tools registered")

    kt = KnowledgeTool(target_registry=registry)

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
            cfg = _load_server_config(server_name)
            base_url = str(cfg.get("base_url", "unknown"))
            resolved_model = str(cfg.get("model", "unknown"))
        except Exception:
            pass
        _info("llm", provider=base_url, model=resolved_model, message="Initializing LLM adapter")
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
