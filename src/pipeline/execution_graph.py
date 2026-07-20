from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline.execution_plan import ExecutionPlan, ExecutionStep


@dataclass(frozen=True, slots=True)
class ExecutionNode:
    """One executable node in the dependency graph.

    An ExecutionNode represents one unit of work within a dependency
    graph. It wraps an ExecutionStep and adds graph-level information:
    which other nodes it depends on.

    This is the first layer where workflow information exists.
    ExecutionStep remains reusable and implementation-independent.

    Attributes:
        execution_step: The work to execute.
        depends_on: Names of capabilities that must complete before
                    this node. Empty means no dependencies.
    """

    execution_step: ExecutionStep
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExecutionGraph:
    """Dependency graph for investigation execution.

    The graph represents the structural relationships between
    execution steps. It owns only topology concerns:
    - what nodes exist
    - which nodes depend on which

    Nodes are stored in execution order.
    Independent nodes (no depends_on) may execute in parallel.

    It does NOT own:
    - runtime scheduling
    - parallel execution
    - batching
    - retry policy
    - tool routing

    Attributes:
        nodes: All nodes in the dependency graph.
    """

    nodes: tuple[ExecutionNode, ...] = ()


class ExecutionGraphBuilder:
    """Build an ExecutionGraph from an ExecutionPlan.

    Responsibilities:
    - convert each ExecutionStep into an ExecutionNode
    - preserve plan insertion order
    - leave independent nodes without dependencies
      (parallel execution is a runtime decision)

    Must not:
    - execute anything
    - route to tools
    - decide parallel execution policy
    - modify the plan

    Input: ExecutionPlan (ordered list of steps)
    Output: ExecutionGraph (dependency graph with nodes)
    """

    def build(self, plan: ExecutionPlan) -> ExecutionGraph:
        """Build an ExecutionGraph from an ExecutionPlan.

        Each execution step becomes one node.
        All nodes are initially independent (no dependencies).
        Insertion order from the plan is preserved.

        Args:
            plan: The ExecutionPlan containing ordered execution steps.

        Returns:
            An ExecutionGraph with one node per step, all independent.
        """
        if not plan.steps:
            return ExecutionGraph()

        nodes: list[ExecutionNode] = [
            ExecutionNode(execution_step=step) for step in plan.steps
        ]

        return ExecutionGraph(nodes=tuple(nodes))
