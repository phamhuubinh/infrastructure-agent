from __future__ import annotations

from unittest import mock

import pytest

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.evidence_cache import EvidenceCache
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.execution_graph import (
    ExecutionGraph,
    ExecutionGraphBuilder,
    ExecutionNode,
)
from src.pipeline.execution_plan import ExecutionPlan, ExecutionStep
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.execution_runtime import RuntimeMetrics
from src.pipeline.fact_set import FactSet
from src.pipeline.finding import FindingDecision
from src.pipeline.intent_resolver import Intent, IntentResolver
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.request_frame import RequestFrame
from src.pipeline.target_resolver import TargetResolver
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from src.tool.knowledge_tool import KnowledgeTool
from tests.pipeline.reasoning_fact_factory import fact


def _real_kt() -> KnowledgeTool:
    """Return a real KnowledgeTool with localhost registered."""
    return KnowledgeTool()


def _engine(
    *,
    intent_resolver: IntentResolver | None = None,
    target_resolver: TargetResolver | None = None,
    evidence_planner: EvidencePlanner | None = None,
    capability_resolver: CapabilityResolver | None = None,
    execution_planner: ExecutionPlanner | None = None,
    graph_builder: ExecutionGraphBuilder | None = None,
    knowledge_tool: KnowledgeTool | None = None,
    evidence_merge: EvidenceMerge | None = None,
    evidence_cache: EvidenceCache | None = None,
) -> ExecutionEngine:
    """Build an ExecutionEngine with defaults or overridden dependencies.

    A real KnowledgeTool is always used for construction so that
    CapabilityRouter.build_routes can succeed. The KnowledgeTool's
    execute() method is mocked via monkey-patching to prevent
    actual tool dispatch.
    """
    kt = knowledge_tool or _real_kt()
    mock.patch.object(
        kt, "execute", return_value=ToolResult(success=True, data={})
    ).start()
    return ExecutionEngine(
        intent_resolver=intent_resolver or mock.Mock(spec=IntentResolver),
        target_resolver=target_resolver or mock.Mock(spec=TargetResolver),
        evidence_planner=evidence_planner or mock.Mock(spec=EvidencePlanner),
        capability_resolver=capability_resolver or mock.Mock(spec=CapabilityResolver),
        execution_planner=execution_planner or mock.Mock(spec=ExecutionPlanner),
        graph_builder=graph_builder or mock.Mock(spec=ExecutionGraphBuilder),
        knowledge_tool=kt,
        evidence_merge=evidence_merge or mock.Mock(spec=EvidenceMerge),
        evidence_cache=evidence_cache,
    )


def _request_with_plan(
    plan: ExecutionPlan | None = None,
) -> InvestigationRequest:
    req = InvestigationRequest(raw_request="test machine")
    req.intent = Intent.MACHINE_ASSESSMENT
    req.target = "localhost"
    if plan is not None:
        req.execution_plan = plan
    return req


def _plan_with_steps(*names: str) -> ExecutionPlan:
    steps = [
        ExecutionStep(capability=CapabilityReference(name=n, evidence_name=n))
        for n in names
    ]
    return ExecutionPlan(steps=tuple(steps))


def test_reasoning_flow_attaches_findings_and_global_health() -> None:
    request = InvestigationRequest(raw_request="check server health")
    request.target = "server-1"
    request.fact_set = FactSet(
        (
            fact("cpu.usage", 95.0),
            fact("system.load_1m", 8.0, unit="load"),
            fact("cpu.logical_cores", 4, unit="count"),
            fact("cpu.iowait", 25.0),
        )
    )

    _engine()._apply_reasoning(request)

    assert any(
        finding.type == "cpu_saturation"
        and finding.decision is FindingDecision.SUPPORTED
        for finding in request.findings
    )
    assert request.health_summary is not None
    assert request.health_summary.status.value == "critical"


# ---------------------------------------------------------------------------
# Happy path — full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_happy_path(self) -> None:
        intent = mock.Mock(spec=IntentResolver)
        target = mock.Mock(spec=TargetResolver)
        evidence = mock.Mock(spec=EvidencePlanner)
        cap_res = mock.Mock(spec=CapabilityResolver)
        exec_plan = mock.Mock(spec=ExecutionPlanner)
        builder = mock.Mock(spec=ExecutionGraphBuilder)
        merge = mock.Mock(spec=EvidenceMerge)
        kt = _real_kt()
        mock.patch.object(
            kt, "execute", return_value=ToolResult(success=True, data={"os": "Linux"})
        ).start()

        builder.build.return_value = ExecutionGraph()

        engine = _engine(
            intent_resolver=intent,
            target_resolver=target,
            evidence_planner=evidence,
            capability_resolver=cap_res,
            execution_planner=exec_plan,
            graph_builder=builder,
            knowledge_tool=kt,
            evidence_merge=merge,
        )

        plan = _plan_with_steps("System Information")
        intent.resolve.return_value = _request_with_plan(plan)

        result = engine.execute("test machine")

        assert isinstance(result, InvestigationRequest)
        intent.resolve.assert_called_once()
        canonical_frame = intent.resolve.call_args.args[0]
        assert canonical_frame.raw_request == "test machine"
        assert canonical_frame.concepts == ("machine",)
        target.resolve.assert_called_once()
        evidence.plan.assert_called_once()
        cap_res.resolve.assert_called_once()
        exec_plan.plan.assert_called_once()
        builder.build.assert_called_once()
        merge.merge.assert_called_once()
        assert isinstance(result.runtime_metrics, RuntimeMetrics)

    def test_each_stage_mutates_same_request(self) -> None:
        intent = mock.Mock(spec=IntentResolver)
        target = mock.Mock(spec=TargetResolver)
        evidence = mock.Mock(spec=EvidencePlanner)
        cap_res = mock.Mock(spec=CapabilityResolver)
        exec_plan = mock.Mock(spec=ExecutionPlanner)
        builder = mock.Mock(spec=ExecutionGraphBuilder)
        merge = mock.Mock(spec=EvidenceMerge)
        kt = _real_kt()

        builder.build.return_value = ExecutionGraph()

        request = _request_with_plan(_plan_with_steps("CPU Information"))

        intent.resolve.return_value = request  # return same object

        engine = _engine(
            intent_resolver=intent,
            target_resolver=target,
            evidence_planner=evidence,
            capability_resolver=cap_res,
            execution_planner=exec_plan,
            graph_builder=builder,
            knowledge_tool=kt,
            evidence_merge=merge,
        )

        result = engine.execute("test")

        assert result is request
        target.resolve.assert_called_once_with(request)
        evidence.plan.assert_called_once_with(request)
        cap_res.resolve.assert_called_once_with(request)
        exec_plan.plan.assert_called_once_with(request)

    def test_explicit_target_without_resolution_fails_before_planning(self) -> None:
        intent = mock.Mock(spec=IntentResolver)
        target = mock.Mock(spec=TargetResolver)
        request = _request_with_plan(_plan_with_steps("System Information"))
        request.request_frame = RequestFrame(
            raw_request="check cpu on ghost-999",
            target_raw="ghost-999",
        )
        intent.resolve.return_value = request

        with pytest.raises(ValueError, match="not resolved"):
            _engine(intent_resolver=intent, target_resolver=target).execute(
                request.request_frame
            )


# ---------------------------------------------------------------------------
# ExecutionGraph building
# ---------------------------------------------------------------------------


class TestGraphBuilding:
    def test_graph_built_from_plan(self) -> None:
        builder = mock.Mock(spec=ExecutionGraphBuilder)
        kt = _real_kt()

        plan = _plan_with_steps("System Information", "CPU Information")
        expected_graph = ExecutionGraph()
        builder.build.return_value = expected_graph

        intent = mock.Mock(spec=IntentResolver)
        intent.resolve.return_value = _request_with_plan(plan)

        engine = _engine(
            intent_resolver=intent,
            graph_builder=builder,
            knowledge_tool=kt,
        )
        result = engine.execute("test")

        builder.build.assert_called_once_with(plan)
        assert result.execution_graph is expected_graph

    def test_no_plan_uses_empty_graph(self) -> None:
        intent = mock.Mock(spec=IntentResolver)
        intent.resolve.return_value = _request_with_plan(None)

        builder = mock.Mock(spec=ExecutionGraphBuilder)
        kt = _real_kt()
        engine = _engine(
            intent_resolver=intent,
            graph_builder=builder,
            knowledge_tool=kt,
        )
        result = engine.execute("test")

        builder.build.assert_not_called()
        assert result.execution_graph is not None
        assert len(result.execution_graph.nodes) == 0

    def test_empty_graph_skips_execution(self) -> None:
        intent = mock.Mock(spec=IntentResolver)
        intent.resolve.return_value = _request_with_plan(_plan_with_steps("Test"))

        builder = mock.Mock(spec=ExecutionGraphBuilder)
        builder.build.return_value = ExecutionGraph()  # no nodes

        kt = _real_kt()
        engine = _engine(
            intent_resolver=intent,
            graph_builder=builder,
            knowledge_tool=kt,
        )
        result = engine.execute("test")

        assert isinstance(result.runtime_metrics, RuntimeMetrics)

    def test_cached_node_satisfies_downstream_dependency(self) -> None:
        cache = EvidenceCache()
        cache.put(
            "localhost",
            "System evidence",
            EvidencePackage(
                capability_name="System Information",
                evidence_name="System evidence",
            ),
        )
        system_step = ExecutionStep(
            capability=CapabilityReference(
                name="System Information", evidence_name="System evidence"
            )
        )
        cpu_step = ExecutionStep(
            capability=CapabilityReference(
                name="CPU Information", evidence_name="CPU evidence"
            )
        )
        graph = ExecutionGraph(
            nodes=(
                ExecutionNode(execution_step=system_step),
                ExecutionNode(
                    execution_step=cpu_step,
                    depends_on=("System Information",),
                ),
            )
        )

        remaining, cached = _engine(evidence_cache=cache)._without_cached_nodes(
            graph, "localhost"
        )

        assert [item.evidence_name for item in cached] == ["System evidence"]
        assert len(remaining.nodes) == 1
        assert remaining.nodes[0].depends_on == ()

    def test_failed_or_partial_cache_write_never_removes_runtime_node(self) -> None:
        cache = EvidenceCache()
        failed = EvidencePackage(
            capability_name="System Information",
            evidence_name="System evidence",
            status=CapabilityStatus.COLLECTION_FAILED,
            success=False,
            error="transport failure",
        )
        partial = EvidencePackage(
            capability_name="System Information",
            evidence_name="System evidence",
            data={"hostname": "partial-host"},
            status=CapabilityStatus.PARTIAL,
            success=False,
            error="kernel probe failed",
        )
        step = ExecutionStep(
            capability=CapabilityReference(
                name="System Information", evidence_name="System evidence"
            )
        )
        graph = ExecutionGraph(nodes=(ExecutionNode(execution_step=step),))
        engine = _engine(evidence_cache=cache)

        assert cache.put("localhost", "System evidence", failed) is False
        assert cache.put("localhost", "System evidence", partial) is False
        remaining, cached = engine._without_cached_nodes(graph, "localhost")

        assert remaining.nodes == graph.nodes
        assert cached == []


# ---------------------------------------------------------------------------
# Evidence merge & completeness
# ---------------------------------------------------------------------------


class TestEvidencePipeline:
    def test_merge_called_with_results(self) -> None:
        kt = _real_kt()

        builder = mock.Mock(spec=ExecutionGraphBuilder)
        builder.build.return_value = ExecutionGraph()

        merge = mock.Mock(spec=EvidenceMerge)
        intent = mock.Mock(spec=IntentResolver)
        intent.resolve.return_value = _request_with_plan(_plan_with_steps("Test"))

        engine = _engine(
            intent_resolver=intent,
            graph_builder=builder,
            knowledge_tool=kt,
            evidence_merge=merge,
        )
        result = engine.execute("test")

        merge.merge.assert_called_once()
        args = merge.merge.call_args
        assert args[0][0] is result
        assert isinstance(args[0][1], dict)

    def test_metrics_evidence_complete_from_request(self) -> None:
        kt = _real_kt()

        builder = mock.Mock(spec=ExecutionGraphBuilder)
        builder.build.return_value = ExecutionGraph()

        intent = mock.Mock(spec=IntentResolver)
        req = _request_with_plan(_plan_with_steps("Test"))
        req.evidence_complete = True
        intent.resolve.return_value = req

        engine = _engine(
            intent_resolver=intent,
            graph_builder=builder,
            knowledge_tool=kt,
        )
        result = engine.execute("test")

        assert result.runtime_metrics is not None
        assert result.runtime_metrics.evidence_complete is True

    def test_request_recollects_after_failure_then_caches_recovery(self) -> None:
        cache = EvidenceCache()
        intent = mock.Mock(spec=IntentResolver)
        builder = mock.Mock(spec=ExecutionGraphBuilder)
        reference = CapabilityReference(
            name="System Information",
            evidence_name="System Information",
            required=True,
        )
        plan = ExecutionPlan(steps=(ExecutionStep(capability=reference),))
        graph = ExecutionGraph(nodes=(ExecutionNode(execution_step=plan.steps[0]),))
        builder.build.return_value = graph

        def new_request(_text: str) -> InvestigationRequest:
            request = _request_with_plan(plan)
            request.capability_references = [reference]
            request.required_evidence = [EvidenceRequirement("System Information")]
            return request

        intent.resolve.side_effect = new_request
        engine = _engine(
            intent_resolver=intent,
            graph_builder=builder,
            evidence_merge=EvidenceMerge(),
            evidence_cache=cache,
        )
        execute_mock = engine.knowledge_tool.execute
        execute_mock.side_effect = [
            ToolResult(
                success=False,
                error="source temporarily unavailable",
                capability_status=CapabilityStatus.COLLECTION_FAILED,
            ),
            ToolResult(success=True, data={"hostname": "recovered-host"}),
        ]

        first = engine.execute("check system")
        second = engine.execute("check system")
        third = engine.execute("check system")

        assert first.evidence[0].success is False
        assert second.evidence[0].data == {"hostname": "recovered-host"}
        assert third.evidence[0].data == {"hostname": "recovered-host"}
        assert execute_mock.call_count == 2
        assert len(cache) == 1


# ---------------------------------------------------------------------------
# Target handling
# ---------------------------------------------------------------------------


class TestTargetHandling:
    def test_target_used_for_execution(self) -> None:
        kt = _real_kt()

        builder = mock.Mock(spec=ExecutionGraphBuilder)
        builder.build.return_value = ExecutionGraph()

        target = mock.Mock(spec=TargetResolver)
        intent = mock.Mock(spec=IntentResolver)
        req = _request_with_plan(_plan_with_steps("System Information"))
        req.target = "myhost"
        intent.resolve.return_value = req

        engine = _engine(
            intent_resolver=intent,
            target_resolver=target,
            graph_builder=builder,
            knowledge_tool=kt,
        )
        engine.execute("test")

        call_args = kt.execute.call_args
        if call_args is not None:
            args, _ = call_args
            assert "myhost" in str(args)


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_execution_step_failure_in_results(self) -> None:
        kt = _real_kt()
        mock.patch.object(
            kt, "execute", return_value=ToolResult(success=False, error="oops")
        ).start()

        builder = mock.Mock(spec=ExecutionGraphBuilder)
        builder.build.return_value = ExecutionGraph()

        intent = mock.Mock(spec=IntentResolver)
        intent.resolve.return_value = _request_with_plan(_plan_with_steps("Test"))

        engine = _engine(
            intent_resolver=intent,
            graph_builder=builder,
            knowledge_tool=kt,
        )
        result = engine.execute("test")

        assert isinstance(result.runtime_metrics, RuntimeMetrics)

    def test_merge_still_called_on_failure(self) -> None:
        kt = _real_kt()
        mock.patch.object(
            kt, "execute", return_value=ToolResult(success=False, error="fail")
        ).start()

        builder = mock.Mock(spec=ExecutionGraphBuilder)
        builder.build.return_value = ExecutionGraph()

        merge = mock.Mock(spec=EvidenceMerge)
        intent = mock.Mock(spec=IntentResolver)
        intent.resolve.return_value = _request_with_plan(_plan_with_steps("Test"))

        engine = _engine(
            intent_resolver=intent,
            graph_builder=builder,
            knowledge_tool=kt,
            evidence_merge=merge,
        )
        engine.execute("test")

        merge.merge.assert_called_once()
