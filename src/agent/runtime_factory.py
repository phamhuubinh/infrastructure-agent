from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.deterministic_agent import DeterministicAgent
from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.llm_assessment_adapter import LLMAssessmentAdapter
from src.model.llm_client import LLMClient
from src.model.mock_assessment_adapter import MockAssessmentAdapter
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


def _load_server_config(
    server_name: str | None = None,
) -> dict[str, object]:
    config_path = Path("servers.json")
    if not config_path.exists():
        raise RuntimeError(
            "servers.json not found. Create a servers.json with model configuration."
        )
    data = json.loads(config_path.read_text())
    servers: dict[str, object] = data.get("servers", {})
    if server_name is None:
        server_name = data.get("active_server", "")
    cfg = servers.get(server_name)
    if cfg is None:
        available = ", ".join(sorted(servers))
        raise RuntimeError(
            f"Server {server_name!r} not found. Available servers: {available}"
        )
    return dict(cfg)


def _load_tools_config() -> dict[str, dict[str, Any]]:
    """Load infrastructure tool configuration from tools.json.

    Returns an empty dict if the file does not exist.
    Each entry must have a "tool" field identifying the type.
    """
    config_path = Path("tools.json")
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text())
        return dict(data) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _register_tools(
    registry: TargetRegistry,
    tools_config: dict[str, dict[str, Any]],
) -> None:
    """Register tools from tools.json into the TargetRegistry.

    Adding a supported tool type here is the only code change needed
    when a new tool domain is added. The tool's credential configuration
    lives in tools.json, not in source code.
    """
    for entry_name, cfg in tools_config.items():
        tool_type = cfg.get("tool")
        if tool_type == "zabbix":
            from src.tool.zabbix_tool import ZabbixTool

            registry.register_tool(
                name=cfg.get("target", entry_name),
                tool=ZabbixTool(
                    url=str(cfg.get("url", "http://localhost/zabbix")),
                    token=str(cfg.get("token", "")),
                    timeout=int(cfg.get("timeout", 10)),
                ),
            )
        elif tool_type == "grafana":
            from src.tool.grafana_tool import GrafanaTool

            registry.register_tool(
                name=cfg.get("target", entry_name),
                tool=GrafanaTool(
                    url=str(cfg.get("url", "http://localhost:3000")),
                    token=str(cfg.get("token", "")),
                    timeout=int(cfg.get("timeout", 10)),
                ),
            )
        # Future tool types can be added here with an elif block.
        # Example:
        # elif tool_type == "vmware":
        #     from src.tool.vmware_tool import VMwareTool
        #     registry.register_tool(name=cfg.get("target", entry_name), tool=VMwareTool(...))


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


def create_deterministic_agent(
    target_store_path: str = "targets.json",
    server_name: str | None = None,
    model: str | None = None,
    assessment_adapter: AssessmentModelAdapter | None = None,
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
    store = TargetStore(path=target_store_path)
    registry = TargetRegistry(store=store)

    # Register infrastructure tools from tools.json (not from hardcoded code).
    tools_config = _load_tools_config()
    _register_tools(registry, tools_config)

    kt = KnowledgeTool(target_registry=registry)

    engine = ExecutionEngine(
        intent_resolver=IntentResolver(),
        target_resolver=TargetResolver(),
        evidence_planner=EvidencePlanner(),
        capability_resolver=CapabilityResolver(),
        execution_planner=ExecutionPlanner(),
        graph_builder=ExecutionGraphBuilder(),
        knowledge_tool=kt,
        evidence_merge=EvidenceMerge(),
    )

    if assessment_adapter is None:
        if server_name or model:
            assessment_adapter = _build_assessment_adapter(
                server_name=server_name,
                model=model,
            )
        else:
            assessment_adapter = MockAssessmentAdapter()

    return DeterministicAgent(
        execution_engine=engine,
        assessment_model=assessment_adapter,
    )
