from __future__ import annotations

from src.pipeline.capability_router import CapabilityRouter
from src.pipeline.execution_graph import ExecutionGraph
from src.pipeline.execution_graph import ExecutionNode
from src.shared.execution.tool_result import ToolResult
from src.tool.knowledge_tool import KnowledgeTool


class ExecutionRuntime:
    """Execute an ExecutionGraph through KnowledgeTool.

    Responsibilities:
    - walk the execution graph respecting dependencies
    - resolve each node to a KnowledgeTool route via CapabilityRouter
    - dispatch through KnowledgeTool
    - collect results
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
    ) -> dict[str, ToolResult]:
        """Execute all nodes in the graph and return collected evidence.

        Nodes are executed respecting dependency order.
        Independent nodes may execute in parallel.
        Failed nodes are recorded but do not terminate execution.

        Args:
            graph: The execution graph to execute.

        Returns:
            A dict mapping capability name to ToolResult.
        """
        if not graph.nodes:
            return {}

        # Build dependency tracking structures.
        completed: set[str] = set()
        results: dict[str, ToolResult] = {}
        remaining = list(graph.nodes)

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
                ready = list(remaining)

            remaining = still_remaining

            if len(ready) == 1:
                node = ready[0]
                cap_name = node.execution_step.capability.name
                result = self._execute_node(node)
                results[cap_name] = result
                if result.success:
                    completed.add(cap_name)
            else:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=len(ready),
                ) as executor:
                    future_map: dict[concurrent.futures.Future, ExecutionNode] = {}
                    for node in ready:
                        future = executor.submit(self._execute_node, node)
                        future_map[future] = node

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

        return results

    def _execute_node(
        self,
        node: ExecutionNode,
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
