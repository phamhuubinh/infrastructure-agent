from __future__ import annotations

import json
from pathlib import Path

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
from src.tool.grafana_tool import GrafanaTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore
from src.tool.zabbix_tool import ZabbixTool


def _load_server_config(
    server_name: str | None = None,
) -> dict[str, object]:
    """Load model server configuration from servers.json."""
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


def _build_assessment_adapter(
    server_name: str | None = None,
    model: str | None = None,
) -> AssessmentModelAdapter:
    """Build the appropriate assessment adapter.

    If a server configuration is available, builds an LLMAssessmentAdapter.
    Otherwise falls back to MockAssessmentAdapter.
    """
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
    register_zabbix: bool = True,
    register_grafana: bool = True,
    server_name: str | None = None,
    model: str | None = None,
    assessment_adapter: AssessmentModelAdapter | None = None,
) -> DeterministicAgent:
    """Build the production deterministic runtime.

    This is the single Composition Root for the deterministic pipeline.
    All entry points (CLI, benchmark, test) construct the runtime here.

    Responsibilities:
    - wire TargetStore → TargetRegistry → KnowledgeTool
    - wire all pipeline components into ExecutionEngine
    - wire ExecutionEngine + AssessmentAdapter into DeterministicAgent

    Args:
        target_store_path: Path to the targets configuration file.
        register_zabbix: Whether to register the Zabbix tool.
        register_grafana: Whether to register the Grafana tool.
        server_name: Name of the model server from servers.json.
        model: Override model name (overrides servers.json model).
        assessment_adapter: Optional pre-built assessment adapter.
                           If None, builds one from server_name/model.

    Returns:
        A fully wired DeterministicAgent ready for execution.
    """
    store = TargetStore(path=target_store_path)
    registry = TargetRegistry(store=store)

    if register_zabbix:
        registry.register_tool(
            name="zabbix",
            tool=ZabbixTool(
                url="http://192.168.10.222/zabbix",
                token="7456fa347e17ce81f8f9d7429c8d4b8c2161b9fe62596d629ad390fdfb7e4eb7",
            ),
        )

    if register_grafana:
        registry.register_tool(
            name="grafana",
            tool=GrafanaTool(),
        )

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
