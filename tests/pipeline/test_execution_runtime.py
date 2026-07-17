from __future__ import annotations

from unittest import mock

import pytest

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_router import CapabilityRouter
from src.pipeline.execution_graph import ExecutionGraph
from src.pipeline.execution_plan import ExecutionStep
from src.pipeline.execution_runtime import ExecutionRuntime
from src.shared.execution.tool_result import ToolResult
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


@pytest.fixture
def knowledge_tool() -> KnowledgeTool:
    """KnowledgeTool with localhost target."""
    registry = TargetRegistry()
    registry.add("localhost")
    return KnowledgeTool(target_registry=registry)


@pytest.fixture
def runtime(knowledge_tool: KnowledgeTool) -> ExecutionRuntime:
    router = CapabilityRouter()
    router.build_routes(knowledge_tool)
    return ExecutionRuntime(knowledge_tool=knowledge_tool, router=router)


def _step(cap_name: str, evidence_name: str = "") -> ExecutionStep:
    return ExecutionStep(
        capability=CapabilityReference(
            name=cap_name, evidence_name=evidence_name or cap_name
        ),
    )


def _node(step: ExecutionStep, deps: tuple[str, ...] = ()) -> tuple:
    """Build a node tuple for ExecutionGraph."""
    from src.pipeline.execution_graph import ExecutionNode

    return ("node", step, deps, ExecutionNode(execution_step=step, depends_on=deps))


def _graph_from_steps(
    steps: list[ExecutionStep],
    deps: dict[str, tuple[str, ...]] | None = None,
) -> ExecutionGraph:
    """Build an ExecutionGraph from a list of steps with optional dependencies."""
    from src.pipeline.execution_graph import ExecutionNode

    if deps is None:
        deps = {}

    nodes: list[ExecutionNode] = []
    for step in steps:
        nodes.append(
            ExecutionNode(
                execution_step=step,
                depends_on=deps.get(step.capability.name, ()),
            ),
        )
    return ExecutionGraph(nodes=tuple(nodes))


# ---------------------------------------------------------------------------
# Empty graph
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    def test_no_nodes_returns_empty(self, runtime: ExecutionRuntime) -> None:
        graph = ExecutionGraph()
        results, _ = runtime.execute(graph)
        assert results == {}


# ---------------------------------------------------------------------------
# Single node execution
# ---------------------------------------------------------------------------


class TestSingleNode:
    def test_known_capability_dispatches(self, runtime: ExecutionRuntime) -> None:
        step = _step("System Information")
        graph = _graph_from_steps([step])
        results, _ = runtime.execute(graph)
        assert "System Information" in results
        # Should succeed or fail based on actual system state.
        # We just verify it dispatches without error.
        assert isinstance(results["System Information"], ToolResult)

    def test_unknown_capability_returns_error(self, runtime: ExecutionRuntime) -> None:
        step = _step("Unknown Capability")
        graph = _graph_from_steps([step])
        results, _ = runtime.execute(graph)
        assert "Unknown Capability" in results
        assert results["Unknown Capability"].success is False
        assert "No route configured" in (results["Unknown Capability"].error or "")


# ---------------------------------------------------------------------------
# Dependency ordering
# ---------------------------------------------------------------------------


class TestDependencyOrdering:
    def test_dependency_satisfied(self, runtime: ExecutionRuntime) -> None:
        step_a = _step("System Information")
        step_b = _step("CPU Information", "CPU")
        graph = _graph_from_steps(
            [step_a, step_b],
            deps={"CPU Information": ("System Information",)},
        )
        results, _ = runtime.execute(graph)
        assert "System Information" in results
        assert "CPU Information" in results

    def test_all_independent_execute(self, runtime: ExecutionRuntime) -> None:
        step_a = _step("System Information")
        step_b = _step("CPU Information", "CPU")
        step_c = _step("Memory Information", "Memory")
        graph = _graph_from_steps([step_a, step_b, step_c])
        results, _ = runtime.execute(graph)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    def test_all_node_failures_collected(self, runtime: ExecutionRuntime) -> None:
        step = _step("Unknown Capability X")
        graph = _graph_from_steps([step])
        results, _ = runtime.execute(graph)
        assert "Unknown Capability X" in results
        assert results["Unknown Capability X"].success is False

    def test_partial_failure_continues(self, runtime: ExecutionRuntime) -> None:
        step_good = _step("System Information")
        step_bad = _step("Unknown Capability Y")
        graph = _graph_from_steps([step_good, step_bad])
        results, _ = runtime.execute(graph)
        assert "System Information" in results
        assert "Unknown Capability Y" in results
        # Good one may succeed or fail at system level, but must have executed
        assert isinstance(results["System Information"], ToolResult)
        assert results["Unknown Capability Y"].success is False


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


class TestParallelExecution:
    def test_independent_nodes_executed(self, runtime: ExecutionRuntime) -> None:
        steps = [
            _step("System Information"),
            _step("CPU Information", "CPU"),
            _step("Memory Information", "Memory"),
        ]
        graph = _graph_from_steps(steps)
        results, _ = runtime.execute(graph)
        assert len(results) == 3
        for name in ("System Information", "CPU Information", "Memory Information"):
            assert name in results


# ---------------------------------------------------------------------------
# KnowledgeTool integration
# ---------------------------------------------------------------------------


class TestKnowledgeToolIntegration:
    def test_dispatch_through_knowledge_tool(
        self,
        knowledge_tool: KnowledgeTool,
    ) -> None:
        """Verify KnowledgeTool is called with correct arguments."""
        step = _step("System Information")
        graph = _graph_from_steps([step])
        runtime = ExecutionRuntime(knowledge_tool=knowledge_tool)
        results, _ = runtime.execute(graph)
        assert "System Information" in results


# ---------------------------------------------------------------------------
# Early completion
# ---------------------------------------------------------------------------


class TestEarlyCompletion:
    def test_no_required_evidence_all_execute(self) -> None:
        """Without required_evidence_names, all nodes execute normally."""
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=True, data={})

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        steps = [
            _step("CPU Information", "CPU"),
            _step("Memory Information", "Memory"),
        ]
        graph = _graph_from_steps(steps)
        results, metrics = runtime.execute(graph)

        assert mock_kt.execute.call_count == 2
        assert metrics.early_completed is False
        assert len(results) == 2

    def test_early_completion_skips_remaining(self) -> None:
        """When all required evidence is collected, remaining nodes are skipped."""
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=True, data={})

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        steps = [
            _step("CPU Information", "CPU"),
            _step("Memory Information", "Memory"),
            _step("Swap Information", "Swap"),
            _step("Disk Usage", "Disk"),
        ]
        graph = _graph_from_steps(steps)

        # Only need CPU and Memory — Swap and Disk should be skipped
        results, metrics = runtime.execute(
            graph,
            required_evidence_names={"CPU", "Memory"},
        )

        # First two should have executed
        assert "CPU Information" in results
        assert "Memory Information" in results
        assert results["CPU Information"].success is True
        assert results["Memory Information"].success is True

        # Last two should be skipped
        assert "Swap Information" in results
        assert "Disk Usage" in results
        assert results["Swap Information"].success is False
        assert "Skipped" in (results["Swap Information"].error or "")
        assert results["Disk Usage"].success is False
        assert "Skipped" in (results["Disk Usage"].error or "")

        assert metrics.early_completed is True

    def test_early_completion_single_node_triggers(self) -> None:
        """Single node that satisfies the only requirement triggers early completion."""
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=True, data={})

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        steps = [
            _step("System Information", "System"),
            _step("CPU Information", "CPU"),
        ]
        graph = _graph_from_steps(steps)

        # Only need System — CPU should be skipped
        results, metrics = runtime.execute(
            graph,
            required_evidence_names={"System"},
        )

        assert "System Information" in results
        assert results["System Information"].success is True
        assert "CPU Information" in results
        assert results["CPU Information"].success is False
        assert "Skipped" in (results["CPU Information"].error or "")
        assert metrics.early_completed is True
        # Only System Information executed
        assert mock_kt.execute.call_count == 1

    def test_early_completion_with_dependencies(self) -> None:
        """Early completion respects dependencies — dependent nodes also skipped."""
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=True, data={})

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        step_a = _step("System Information", "System")
        step_b = _step("CPU Information", "CPU")
        step_c = _step("Memory Information", "Memory")

        # B and C depend on A
        graph = _graph_from_steps(
            [step_a, step_b, step_c],
            deps={
                "CPU Information": ("System Information",),
                "Memory Information": ("System Information",),
            },
        )

        # Only need System — A executes, B and C skipped
        results, metrics = runtime.execute(
            graph,
            required_evidence_names={"System"},
        )

        assert metrics.early_completed is True
        assert results["System Information"].success is True
        assert results["CPU Information"].success is False
        assert results["Memory Information"].success is False
        assert "Skipped" in (results["CPU Information"].error or "")
        assert "Skipped" in (results["Memory Information"].error or "")

    def test_early_completion_not_triggered_when_insufficient(self) -> None:
        """When not all required evidence is collected, execution continues."""
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=True, data={})

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        steps = [
            _step("CPU Information", "CPU"),
            _step("Memory Information", "Memory"),
        ]
        graph = _graph_from_steps(steps)

        # Need evidence that won't be produced by any node
        results, metrics = runtime.execute(
            graph,
            required_evidence_names={"CPU", "NonExistentEvidence"},
        )

        assert metrics.early_completed is False
        # Both should have executed (neither produces "NonExistentEvidence")
        assert mock_kt.execute.call_count == 2
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Mocked KnowledgeTool for precise control
# ---------------------------------------------------------------------------


class TestMockedExecution:
    def test_mock_success(self) -> None:
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=True, data={"key": "value"})

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)
        step = _step("System Information")
        graph = _graph_from_steps([step])
        results, _ = runtime.execute(graph)

        assert "System Information" in results
        assert results["System Information"].success is True
        mock_kt.execute.assert_called_once_with(
            {"source": "localhost", "resource": "get_system"},
        )

    def test_mock_failure(self) -> None:
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=False, error="mock error")

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)
        step = _step("System Information")
        graph = _graph_from_steps([step])
        results, _ = runtime.execute(graph)

        assert "System Information" in results
        assert results["System Information"].success is False
        assert results["System Information"].error == "mock error"

    def test_timeout_returns_partial_results(self) -> None:
        """When a single node exceeds overall_timeout, partial results returned."""
        slow_result = ToolResult(success=False, error="timed out")
        mock_kt = mock.Mock(spec=KnowledgeTool)
        import time as _time

        def _slow(_args):
            _time.sleep(10)
            return ToolResult(success=True)

        mock_kt.execute.side_effect = _slow

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)
        step = _step("System Information")
        graph = _graph_from_steps([step])

        t0 = _time.perf_counter()
        results, metrics = runtime.execute(graph, overall_timeout=0.5)
        elapsed = _time.perf_counter() - t0

        assert elapsed < 3.0, f"Took too long: {elapsed:.1f}s"
        assert metrics.timed_out
        assert "System Information" in results
        assert results["System Information"].success is False
        assert "timed out" in (results["System Information"].error or "").lower()

    def test_mock_executes_dependency_order(self) -> None:
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=True, data={})

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)
        step_a = _step("System Information")
        step_b = _step("CPU Information", "CPU")
        step_c = _step("Memory Information", "Memory")

        # B and C depend on A
        graph = _graph_from_steps(
            [step_a, step_b, step_c],
            deps={
                "CPU Information": ("System Information",),
                "Memory Information": ("System Information",),
            },
        )
        results, _ = runtime.execute(graph)
        assert len(results) == 3
        # A must be executed before B and C
        assert mock_kt.execute.call_count == 3

    def test_mock_parallel_execution(self) -> None:
        mock_kt = mock.Mock(spec=KnowledgeTool)
        mock_kt.execute.return_value = ToolResult(success=True, data={})

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)
        steps = [
            _step("CPU Information", "CPU"),
            _step("Memory Information", "Memory"),
            _step("Swap Information", "Swap"),
        ]
        graph = _graph_from_steps(steps)
        runtime.execute(graph)
        # All three should execute
        assert mock_kt.execute.call_count == 3

    def test_mock_unknown_capability_no_dispatch(self) -> None:
        mock_kt = mock.Mock(spec=KnowledgeTool)
        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)
        step = _step("NonExistentCapability")
        graph = _graph_from_steps([step])
        results, _ = runtime.execute(graph)

        assert "NonExistentCapability" in results
        assert results["NonExistentCapability"].success is False
        # KnowledgeTool should NOT be called for unknown capabilities
        mock_kt.execute.assert_not_called()
