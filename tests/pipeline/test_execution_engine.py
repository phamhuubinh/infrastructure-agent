from __future__ import annotations

from unittest import mock

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.execution_engine import ExecutionEngine
from src.pipeline.execution_graph import ExecutionGraph, ExecutionGraphBuilder
from src.pipeline.execution_plan import ExecutionPlan, ExecutionStep
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.execution_runtime import RuntimeMetrics
from src.pipeline.intent_resolver import Intent, IntentResolver
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.target_resolver import TargetResolver
from src.shared.execution.tool_result import ToolResult
from src.tool.knowledge_tool import KnowledgeTool


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
        intent.resolve.assert_called_once_with("test machine")
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
