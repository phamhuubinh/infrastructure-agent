from __future__ import annotations

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.execution_graph import (
    ExecutionGraph,
    ExecutionGraphBuilder,
    ExecutionNode,
)
from src.pipeline.execution_plan import ExecutionPlan, ExecutionStep


def _step(cap_name: str, evidence_name: str = "") -> ExecutionStep:
    return ExecutionStep(
        capability=CapabilityReference(
            name=cap_name,
            evidence_name=evidence_name or cap_name,
        ),
    )


def _plan(steps: list[ExecutionStep]) -> ExecutionPlan:
    return ExecutionPlan(steps=tuple(steps))


def _node_names(graph: ExecutionGraph) -> list[str]:
    return [n.execution_step.capability.name for n in graph.nodes]


def _node_deps(graph: ExecutionGraph) -> dict[str, tuple[str, ...]]:
    return {n.execution_step.capability.name: n.depends_on for n in graph.nodes}


class TestBuilder:
    """ExecutionGraphBuilder produces correct graphs from plans."""

    def test_empty_plan(self) -> None:
        builder = ExecutionGraphBuilder()
        plan = _plan([])
        graph = builder.build(plan)
        assert graph.nodes == ()
        assert len(graph.nodes) == 0

    def test_single_step(self) -> None:
        builder = ExecutionGraphBuilder()
        step = _step("CPU Information")
        graph = builder.build(_plan([step]))
        assert len(graph.nodes) == 1
        assert graph.nodes[0].execution_step.capability.name == "CPU Information"
        assert graph.nodes[0].depends_on == ()

    def test_multiple_independent_steps(self) -> None:
        builder = ExecutionGraphBuilder()
        steps = [
            _step("CPU Information"),
            _step("Memory Information"),
            _step("Service Status"),
        ]
        graph = builder.build(_plan(steps))
        assert len(graph.nodes) == 3
        assert _node_names(graph) == [
            "CPU Information",
            "Memory Information",
            "Service Status",
        ]

    def test_all_nodes_independent(self) -> None:
        builder = ExecutionGraphBuilder()
        steps = [
            _step("CPU Information"),
            _step("Memory Information"),
            _step("Service Status"),
        ]
        graph = builder.build(_plan(steps))
        deps = _node_deps(graph)
        for cap_name, dep_tuple in deps.items():
            assert dep_tuple == (), f"{cap_name} has dependencies: {dep_tuple}"

    def test_preserves_insertion_order(self) -> None:
        builder = ExecutionGraphBuilder()
        steps = [
            _step("Service Status"),
            _step("CPU Information"),
            _step("Package Discovery"),
        ]
        graph = builder.build(_plan(steps))
        assert _node_names(graph) == [
            "Service Status",
            "CPU Information",
            "Package Discovery",
        ]

    def test_deterministic(self) -> None:
        builder = ExecutionGraphBuilder()
        steps = [
            _step("CPU Information"),
            _step("Memory Information"),
        ]
        plan = _plan(steps)
        g1 = builder.build(plan)
        g2 = builder.build(plan)
        assert g1.nodes == g2.nodes

    def test_idempotent(self) -> None:
        builder = ExecutionGraphBuilder()
        step = _step("CPU Information")
        plan = _plan([step])
        g1 = builder.build(plan)
        g2 = builder.build(plan)
        assert g1 == g2

    def test_step_metadata_preserved(self) -> None:
        builder = ExecutionGraphBuilder()
        step = _step("CPU Information", evidence_name="CPU")
        step2 = ExecutionStep(
            capability=CapabilityReference(
                name="Memory Information", evidence_name="Memory"
            ),
            step_id="mem-1",
            metadata={"domain": "linux"},
        )
        graph = builder.build(_plan([step, step2]))
        assert graph.nodes[0].execution_step.capability.evidence_name == "CPU"
        assert graph.nodes[1].execution_step.step_id == "mem-1"
        assert graph.nodes[1].execution_step.metadata["domain"] == "linux"


class TestNodeProperties:
    """ExecutionNode properties are correct."""

    def test_frozen(self) -> None:
        step = _step("CPU Information")
        node = ExecutionNode(execution_step=step)
        with pytest.raises(AttributeError):
            node.depends_on = ("other",)  # type: ignore[misc]

    def test_depends_on_optional(self) -> None:
        step = _step("CPU Information")
        node = ExecutionNode(execution_step=step)
        assert node.depends_on == ()

    def test_depends_on_with_deps(self) -> None:
        step = _step("CPU Information")
        node = ExecutionNode(execution_step=step, depends_on=("System Information",))
        assert node.depends_on == ("System Information",)

    def test_repr(self) -> None:
        step = _step("CPU Information")
        node = ExecutionNode(execution_step=step)
        assert "CPU Information" in repr(node)


class TestGraphProperties:
    """ExecutionGraph properties are correct."""

    def test_empty_graph(self) -> None:
        g = ExecutionGraph()
        assert g.nodes == ()

    def test_frozen(self) -> None:
        step = _step("CPU Information")
        node = ExecutionNode(execution_step=step)
        g = ExecutionGraph(nodes=(node,))
        with pytest.raises(AttributeError):
            g.nodes = ()  # type: ignore[misc]


class TestRuntimeExecutionEdgeCases:
    """Additional execution graph processing behaviors (regression tests)."""

    def test_graph_with_single_node_no_deps(self) -> None:
        """Single node with no dependencies still builds correctly."""
        step = _step("CPU Information")
        graph = ExecutionGraphBuilder().build(_plan([step]))
        assert len(graph.nodes) == 1
        assert graph.nodes[0].depends_on == ()

    def test_graph_preserves_all_metadata(self) -> None:
        """Regression: all step metadata must survive graph building."""
        step = ExecutionStep(
            capability=CapabilityReference(
                name="CPU Information",
                evidence_name="CPU",
                description="Check CPU info",
                supported_targets=("linux",),
                parameters=("source",),
                estimated_cost=0.5,
            ),
            step_id="cpu-1",
            metadata={"domain": "linux", "timeout": 30},
        )
        graph = ExecutionGraphBuilder().build(_plan([step]))
        node = graph.nodes[0]
        cap = node.execution_step.capability
        assert cap.name == "CPU Information"
        assert cap.evidence_name == "CPU"
        assert cap.description == "Check CPU info"
        assert cap.supported_targets == ("linux",)
        assert cap.parameters == ("source",)
        assert cap.estimated_cost == 0.5
        assert node.execution_step.step_id == "cpu-1"
        assert node.execution_step.metadata == {"domain": "linux", "timeout": 30}

    def test_multiple_steps_no_deps_all_independent(self) -> None:
        """All nodes in graph with no deps should be independent."""
        steps = [
            _step("A"),
            _step("B"),
            _step("C"),
            _step("D"),
        ]
        graph = ExecutionGraphBuilder().build(_plan(steps))
        for node in graph.nodes:
            assert node.depends_on == ()

    def test_frozen_node_prevents_mutation(self) -> None:
        """Regression: ExecutionNode must remain frozen."""
        step = _step("CPU Information")
        node = ExecutionNode(execution_step=step)
        with pytest.raises(AttributeError):
            node.execution_step = step  # type: ignore[misc]

    def test_frozen_graph_prevents_mutation(self) -> None:
        """Regression: ExecutionGraph must remain frozen."""
        step = _step("CPU Information")
        node = ExecutionNode(execution_step=step)
        g = ExecutionGraph(nodes=(node,))
        with pytest.raises(AttributeError):
            g.nodes = ()  # type: ignore[misc]


class TestFullPipelineGraph:
    """Verify the builder integrates with the full pipeline."""

    def test_machine_assessment_produces_graph(self) -> None:
        from src.pipeline.capability_resolver import CapabilityResolver
        from src.pipeline.evidence_planner import EvidencePlanner
        from src.pipeline.execution_planner import ExecutionPlanner
        from src.pipeline.intent_resolver import IntentResolver
        from src.pipeline.target_resolver import TargetResolver
        from src.tool.target_registry import TargetRegistry

        resolver = IntentResolver()
        request = resolver.resolve("check the server health")
        registry = TargetRegistry()
        registry.add("server01")
        TargetResolver(target_registry=registry).resolve(request)
        EvidencePlanner().plan(request)
        CapabilityResolver().resolve(request)
        ExecutionPlanner().plan(request)

        builder = ExecutionGraphBuilder()
        assert request.execution_plan is not None
        graph = builder.build(request.execution_plan)

        assert len(graph.nodes) > 0
        names = _node_names(graph)
        assert "CPU Information" in names
        assert "Memory Information" in names
        assert "Service Status" in names

    def test_runtime_executes_graph(self) -> None:
        """Full integration: pipeline → graph → runtime → evidence."""
        from src.pipeline.capability_resolver import CapabilityResolver
        from src.pipeline.evidence_merge import EvidenceMerge
        from src.pipeline.evidence_planner import EvidencePlanner
        from src.pipeline.execution_engine import ExecutionEngine
        from src.pipeline.execution_planner import ExecutionPlanner
        from src.pipeline.intent_resolver import IntentResolver
        from src.pipeline.target_resolver import TargetResolver
        from src.tool.knowledge_tool import KnowledgeTool
        from src.tool.target_registry import TargetRegistry

        registry = TargetRegistry()
        registry.add("localhost")
        registry.add("server01")
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

        request = engine.execute("check the server health")
        assert request.execution_graph is not None
        assert len(request.execution_graph.nodes) > 0
        assert len(request.evidence) > 0
        assert any(p.success for p in request.evidence)


# Required for TestNodeProperties frozen test
import pytest  # noqa: E402, F811
