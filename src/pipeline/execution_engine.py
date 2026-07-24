from __future__ import annotations

from src.pipeline.capability_planner import CapabilityPlanner
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.evidence_cache import EvidenceCache
from src.pipeline.evidence_completeness import EvidenceCompleteness
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.execution_graph import ExecutionGraph, ExecutionGraphBuilder
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.execution_runtime import ExecutionRuntime, RuntimeMetrics
from src.pipeline.intent_resolver import IntentResolver
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.target_resolver import TargetResolver
from src.shared.execution.tool_result import ToolResult
from src.tool.knowledge_tool import KnowledgeTool


class ExecutionEngine:
    """Coordinate investigation execution.

    6-stage pipeline: Normalize → Target → Plan → Graph → Execute → Assess.

    Responsibilities:
    - Stage 0: Normalize user language → SemanticRequest (Normalizer)
    - Stage 1: Resolve investigation target (TargetResolver)
    - Stage 2: Select evidence + capability plan (EvidencePlanner + CapabilityPlanner)
    - Stage 3: Build execution graph (ExecutionPlanner + GraphBuilder)
    - Stage 4: Dispatch to KnowledgeTool, collect evidence (ExecutionRuntime)
    - Stage 5: Merge evidence (EvidenceMerge + EvidenceCompleteness)

    Never performs reasoning or assessment.
    """

    @property
    def knowledge_tool(self) -> KnowledgeTool:
        return self._knowledge_tool

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
        evidence_cache: EvidenceCache | None = None,
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
        self._capability_planner = CapabilityPlanner()
        self._evidence_cache = evidence_cache
        self._runtime = ExecutionRuntime(knowledge_tool=knowledge_tool)
        self._runtime.router.build_routes(knowledge_tool)

    def execute(self, user_request: str) -> InvestigationRequest:
        """Execute a full 6-stage investigation from request to evidence.

        Stage 0: Normalize → SemanticRequest (language only, no capabilities).
        Stage 1: Target → resolve target name.
        Stage 2: Plan → evidence templates + capability plan.
        Stage 3: Graph → execution plan + graph build.
        Stage 4: Execute → dispatch to KnowledgeTool, collect evidence.
        Stage 5: Merge → merge evidence + completeness check.
        """
        # Stage 0: Normalize user language into structured SemanticRequest.
        from src.pipeline.normalizer import Normalizer

        normalizer = Normalizer()
        semantic = normalizer.normalize(user_request)

        # Stage 1: Resolve intent using the classic keyword-based resolver.
        request = self._intent_resolver.resolve(user_request)

        # Attach the semantic request to the investigation for downstream use.
        request.semantic_request = semantic

        # Phase 6: Extract parameters from the user request.
        from src.pipeline.parameter_extractor import ParameterExtractor

        param_extractor = ParameterExtractor()
        request.extracted_params = param_extractor.extract(user_request)

        # Phase 6: Classify answer type.
        from src.pipeline.answer_type import AnswerTypeClassifier

        classifier = AnswerTypeClassifier()
        request.answer_type = classifier.classify(user_request)

        # Phase 6: Select tool for evidence collection.
        from src.pipeline.tool_selector import ToolSelector

        tool_selector = ToolSelector()
        request.selected_tool = tool_selector.select(user_request, semantic.concept)

        # Stage 2: Resolve target.
        self._target_resolver.resolve(request)

        # Stage 3: Plan evidence + capabilities.
        self._evidence_planner.plan(request)
        self._capability_resolver.resolve(request)

        # Phase 6: Augment capability resolution with CapabilityPlanner.
        # When Normalizer confidence >= 0.4, use CapabilityPlanner to filter
        # capability_references to only the planned capabilities.
        if semantic.confidence >= 0.4:
            planned_names = set(self._capability_planner.plan(semantic))
            if planned_names:
                filtered = [
                    ref
                    for ref in request.capability_references
                    if ref.evidence_name in planned_names
                ]
                if filtered:
                    request.capability_references = filtered

        self._execution_planner.plan(request)

        # Stage 4: Build execution graph.
        if request.execution_plan is not None:
            graph = self._graph_builder.build(request.execution_plan)
        else:
            graph = ExecutionGraph()
        request.execution_graph = graph

        # Stage 5: Execute the graph through the runtime.
        if graph.nodes:
            target = request.target or "localhost"
            required_evidence = {
                ref.evidence_name
                for ref in request.capability_references
                if ref.required
            }
            # Phase 6: Pass extracted params to runtime for filtered evidence collection.
            extracted_params = getattr(request, "extracted_params", None)
            results, metrics = self._runtime.execute(
                graph,
                target=target,
                required_evidence_names=required_evidence,
                extracted_params=extracted_params,
            )
        else:
            results, metrics = {}, RuntimeMetrics()

        # Stage 6: Merge evidence + completeness.
        self._merge(request, results)
        self._evidence_completeness.check(request)

        # Phase 6: Cache collected evidence for reuse across turns.
        if self._evidence_cache is not None:
            for pkg in request.evidence:
                if pkg.success:
                    self._evidence_cache.put(pkg.evidence_name, pkg)

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
        # Phase 6: Tag evidence packages with the selected tool to prevent
        # cross-contamination (e.g., Linux evidence appearing in Grafana context).
        selected_tool = getattr(request, "selected_tool", None)
        source_tool = selected_tool.name.lower() if selected_tool else None
        self._evidence_merge.merge(request, results, source_tool=source_tool)
