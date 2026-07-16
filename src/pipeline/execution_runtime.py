from __future__ import annotations

import time as _time

from dataclasses import dataclass
from dataclasses import field

from src.pipeline.capability_router import CapabilityRouter
from src.pipeline.execution_graph import ExecutionGraph
from src.pipeline.execution_graph import ExecutionNode
from src.shared.execution.tool_result import ToolResult
from src.tool.knowledge_tool import KnowledgeTool


@dataclass
class RuntimeMetrics:
    """Aggregated runtime execution metrics.

    Collected during graph execution without affecting execution flow.

    Attributes:
        execution_duration: Wall-clock time in seconds for graph execution.
        total_nodes: Number of nodes in the graph.
        successful_nodes: Number of nodes that completed successfully.
        failed_nodes: Number of nodes that failed.
        parallel_ratio: Fraction of nodes that executed in parallel
                        (1.0 = all parallel, 0.0 = all sequential).
        tool_calls: Number of KnowledgeTool dispatch calls made.
        evidence_complete: Whether all required evidence was collected.
    """

    execution_duration: float = 0.0
    total_nodes: int = 0
    successful_nodes: int = 0
    failed_nodes: int = 0
    parallel_ratio: float = 0.0
    tool_calls: int = 0
    evidence_complete: bool = False


class ExecutionRuntime:
    """Execute an ExecutionGraph through KnowledgeTool.

    Responsibilities:
    - walk the execution graph respecting dependencies
    - resolve each node to a KnowledgeTool route via CapabilityRouter
    - dispatch through KnowledgeTool
    - collect results
    - collect runtime metrics
    - handle failures without terminating the investigation

    Never performs reasoning or assessment.
    """

    def __init__(
        self,
        knowledge_tool: KnowledgeTool,
        router: CapabilityRouter | None = None,
    ) -> None:
        self._knowledge_tool = knowledge_tool
        self._router = router or CapabilityRouter()

    @property
    def router(self) -> CapabilityRouter:
        """Access the router for route building."""
        return self._router

    def execute(
        self,
        graph: ExecutionGraph,
        target: str = "localhost",
    ) -> tuple[dict[str, ToolResult], RuntimeMetrics]:
        """Execute all nodes in the graph and return collected evidence.

        Nodes are executed respecting dependency order.
        Independent nodes may execute in parallel.
        Failed nodes are recorded but do not terminate execution.

        Returns both results and runtime metrics.

        Args:
            graph: The execution graph to execute.

        Returns:
            A tuple of (results dict, RuntimeMetrics).
        """
        metrics = RuntimeMetrics()
        t0 = _time.perf_counter()

        if not graph.nodes:
            metrics.execution_duration = _time.perf_counter() - t0
            return {}, metrics

        metrics.total_nodes = len(graph.nodes)

        completed: set[str] = set()
        results: dict[str, ToolResult] = {}
        remaining = list(graph.nodes)
        max_parallel_batch = 1
        total_nodes_in_parallel = 0

        import concurrent.futures

        while remaining:
            ready: list[ExecutionNode] = []
            still_remaining: list[ExecutionNode] = []

            for node in remaining:
                cap_name = node.execution_step.capability.name
                deps = node.depends_on

                if all(dep in completed for dep in deps):
                    ready.append(node)
                else:
                    still_remaining.append(node)

            if not ready:
                still_remaining.clear()
                ready = [remaining.pop(0)]
                remaining = still_remaining

            if len(ready) > max_parallel_batch:
                max_parallel_batch = len(ready)

            if len(ready) > 1:
                total_nodes_in_parallel += len(ready)

            if len(ready) == 1:
                node = ready[0]
                cap_name = node.execution_step.capability.name
                result = self._execute_node(node, target=target)
                metrics.tool_calls += 1
                results[cap_name] = result
                if result.success:
                    completed.add(cap_name)
            else:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=len(ready),
                ) as executor:
                    future_map: dict[concurrent.futures.Future, ExecutionNode] = {}
                    for node in ready:
                        future = executor.submit(self._execute_node, node, target=target)
                        future_map[future] = node
                        metrics.tool_calls += 1

                    for future in concurrent.futures.as_completed(future_map):
                        node = future_map[future]
                        cap_name = node.execution_step.capability.name
                        try:
                            result = future.result()
                        except Exception as exc:
                            result = ToolResult(
                                success=False,
                                error=f"Execution runtime error: {exc}",
                            )
                        results[cap_name] = result
                        if result.success:
                            completed.add(cap_name)

        metrics.execution_duration = _time.perf_counter() - t0
        metrics.successful_nodes = sum(
            1 for r in results.values() if r.success
        )
        metrics.failed_nodes = sum(
            1 for r in results.values() if not r.success
        )
        if metrics.total_nodes > 0:
            metrics.parallel_ratio = (
                total_nodes_in_parallel / metrics.total_nodes
            )

        return results, metrics

    def _execute_node(
        self,
        node: ExecutionNode,
        target: str = "localhost",
    ) -> ToolResult:
        """Execute a single node by dispatching through KnowledgeTool."""
        cap_name = node.execution_step.capability.name

        route = self._router.resolve(cap_name)
        if route is None:
            return ToolResult(
                success=False,
                error=f"No route configured for capability: {cap_name}",
            )

        source, resource = route

        # If the route points to localhost but the investigation target is
        # a remote machine, override the source with the real target.
        # Domain-specific routes (zabbix, grafana) are preserved as-is.
        if source == "localhost" and target != "localhost":
            source = target

        arguments: dict[str, object] = {
            "source": source,
            "resource": resource,
        }

        try:
            return self._knowledge_tool.execute(arguments)
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"KnowledgeTool dispatch failed for {cap_name}: {exc}",
            )
