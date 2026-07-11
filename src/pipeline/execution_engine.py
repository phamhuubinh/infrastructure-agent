from __future__ import annotations

from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.evidence_completeness import EvidenceCompleteness
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.execution_graph import ExecutionGraph
from src.pipeline.execution_graph import ExecutionGraphBuilder
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.execution_runtime import ExecutionRuntime
from src.pipeline.execution_runtime import RuntimeMetrics
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.intent_resolver import IntentResolver
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.target_resolver import TargetResolver
from src.tool.knowledge_tool import KnowledgeTool


class ExecutionEngine:
    """Coordinate investigation execution.

    Responsibilities:
    - resolve user intent
    - resolve investigation target
    - select evidence templates
    - resolve capabilities
    - plan execution order
    - build execution graphs
    - dispatch to KnowledgeTool
    - collect evidence
    - merge evidence

    Never performs reasoning or assessment.
    """

    def __init__(
        self,
        intent_resolver: IntentResolver,
        target_resolver: TargetResolver,
        evidence_planner: EvidencePlanner,
        capability_resolver: CapabilityResolver,
        execution_planner: ExecutionPlanner,
        graph_builder: ExecutionGraphBuilder,
        knowledge_tool: KnowledgeTool,
        evidence_merge: EvidenceMerge,
    ) -> None:
        self._intent_resolver = intent_resolver
        self._target_resolver = target_resolver
        self._evidence_planner = evidence_planner
        self._capability_resolver = capability_resolver
        self._execution_planner = execution_planner
        self._graph_builder = graph_builder
        self._knowledge_tool = knowledge_tool
        self._evidence_merge = evidence_merge
        self._evidence_completeness = EvidenceCompleteness()
        self._runtime = ExecutionRuntime(knowledge_tool=knowledge_tool)
        self._runtime.router.build_routes(knowledge_tool)

    def execute(self, user_request: str) -> InvestigationRequest:
        """Execute a full investigation from request to evidence.

        Each stage enriches the same InvestigationRequest object.
        The final stage dispatches the execution graph through
        KnowledgeTool and collects evidence.
        """
        request = self._intent_resolver.resolve(user_request)
        self._target_resolver.resolve(request)
        self._evidence_planner.plan(request)
        self._capability_resolver.resolve(request)
        self._execution_planner.plan(request)

        if request.execution_plan is not None:
            graph = self._graph_builder.build(request.execution_plan)
        else:
            graph = ExecutionGraph()
        request.execution_graph = graph

        # Execute the graph through the runtime.
        if graph.nodes:
            results, metrics = self._runtime.execute(graph)
        else:
            results, metrics = {}, RuntimeMetrics()

        self._merge(request, results)
        self._evidence_completeness.check(request)

        # Attach metrics to the request for observability.
        metrics.evidence_complete = request.evidence_complete
        request.runtime_metrics = metrics

        return request

    def _merge(
        self,
        request: InvestigationRequest,
        results: dict[str, ToolResult],
    ) -> None:
        """Merge collected evidence into the investigation request."""
        self._evidence_merge.merge(request, results)
