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

    Supports both mutable (legacy) and immutable (PipelineState) execution paths.
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

    # ------------------------------------------------------------------
    # Immutable PipelineState execution path.
    # Each stage returns a StateUpdate dict; the engine merges them.
    # ------------------------------------------------------------------

    def execute_immutable(self, user_request: str) -> object:
        """Execute the pipeline using immutable PipelineState.

        Each stage returns a StateUpdate (partial dict of fields).
        The engine accumulates them, producing a new PipelineState at each step.

        Returns:
            A PipelineState with all accumulated fields.
        """
        from src.pipeline.answer_type import AnswerTypeClassifier
        from src.pipeline.normalizer import Normalizer
        from src.pipeline.parameter_extractor import ParameterExtractor
        from src.pipeline.tool_selector import ToolSelector
        from src.shared.pipeline_state import PipelineState

        state = PipelineState.initial(user_request)

        # Stage 0: Normalize
        normalizer = Normalizer()
        update = normalizer.normalize_state(state)
        state = state.apply(update)

        # Stage 1: Resolve intent
        update = self._intent_resolver.resolve_state(state)
        state = state.apply(update)

        # Phase 6: Extract parameters
        param_extractor = ParameterExtractor()
        state = state.apply({"extracted_params": param_extractor.extract(user_request)})

        # Phase 6: Classify answer type
        classifier = AnswerTypeClassifier()
        state = state.apply({"answer_type": classifier.classify(user_request)})

        # Phase 6: Select tool
        tool_selector = ToolSelector()
        semantic = state.semantic_request
        state = state.apply(
            {"selected_tool": tool_selector.select(user_request, semantic.concept)}
        )

        # Stage 2: Resolve target
        update = self._target_resolver.resolve_state(state)
        state = state.apply(update)

        # Stage 3: Plan evidence + capabilities
        update = self._evidence_planner.plan_state(state)
        state = state.apply(update)

        update = self._capability_resolver.resolve_state(state)
        state = state.apply(update)

        # Phase 6: Augment with CapabilityPlanner
        semantic = state.semantic_request
        if semantic.confidence >= 0.4:
            planned_names = set(self._capability_planner.plan(semantic))
            if planned_names:
                filtered = tuple(
                    ref
                    for ref in state.capability_references
                    if ref.evidence_name in planned_names
                )
                if filtered:
                    state = state.apply({"capability_references": filtered})

        # Build execution plan and graph
        from src.pipeline.investigation_request import InvestigationRequest

        temp_req = InvestigationRequest(
            raw_request=state.user_request,
            intent=state.intent,
            confidence=state.confidence,
            matched_keywords=state.matched_keywords,
            target=state.target or None,
            required_evidence=list(state.required_evidence),
            optional_evidence=list(state.optional_evidence),
            capability_references=list(state.capability_references),
        )
        self._execution_planner.plan(temp_req)
        state = state.apply({"execution_plan": temp_req.execution_plan})

        if temp_req.execution_plan is not None:
            graph = self._graph_builder.build(temp_req.execution_plan)
        else:
            graph = ExecutionGraph()
        state = state.apply({"execution_graph": graph})

        # Execute graph
        if graph.nodes:
            target = state.target or "localhost"
            required_evidence = {
                ref.evidence_name for ref in state.capability_references if ref.required
            }
            extracted_params = state.extracted_params
            results, metrics = self._runtime.execute(
                graph,
                target=target,
                required_evidence_names=required_evidence,
                extracted_params=extracted_params,
            )
        else:
            results, metrics = {}, RuntimeMetrics()

        # Merge evidence
        self._evidence_merge.merge(temp_req, results)
        state = state.apply({"evidence": tuple(temp_req.evidence)})

        # Completeness check
        self._evidence_completeness.check(temp_req)
        state = state.apply(
            {
                "evidence_complete": temp_req.evidence_complete,
                "missing_evidence": temp_req.missing_evidence,
            }
        )

        # Cache evidence (with target for cross-machine isolation).
        if self._evidence_cache is not None:
            _target = state.target or "localhost"
            for pkg in temp_req.evidence:
                if pkg.success:
                    self._evidence_cache.put(_target, pkg.evidence_name, pkg)

        # Attach metrics
        metrics.evidence_complete = temp_req.evidence_complete
        state = state.apply({"runtime_metrics": metrics})

        return state

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
            _target = request.target or "localhost"
            for pkg in request.evidence:
                if pkg.success:
                    self._evidence_cache.put(_target, pkg.evidence_name, pkg)

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
