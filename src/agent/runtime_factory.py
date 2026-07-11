from __future__ import annotations

from src.agent.deterministic_agent import DeterministicAgent
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


def create_deterministic_agent(
    target_store_path: str = "targets.json",
    register_zabbix: bool = True,
    register_grafana: bool = True,
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

    return DeterministicAgent(
        execution_engine=engine,
        assessment_model=MockAssessmentAdapter(),
    )
