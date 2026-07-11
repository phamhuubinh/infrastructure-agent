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
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


def test_deterministic_agent_runs_pipeline() -> None:
    registry = TargetRegistry()
    registry.add("localhost")
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

    agent = DeterministicAgent(
        execution_engine=engine,
        assessment_model=MockAssessmentAdapter(),
    )

    result = agent.run("check the server health")
    assert "Investigation: check the server health" in result
    assert "Evidence collected: 13" in result
    assert "Successful: 12" in result
    assert "Failed: 1" in result
    assert "Evidence complete: True" in result


def test_pipeline_only() -> None:
    registry = TargetRegistry()
    registry.add("localhost")
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

    agent = DeterministicAgent(
        execution_engine=engine,
        assessment_model=MockAssessmentAdapter(),
    )

    request = agent.execute_pipeline_only("check the server health")
    assert len(request.evidence) > 0
    assert request.intent is not None
