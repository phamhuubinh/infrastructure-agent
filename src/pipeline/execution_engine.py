from __future__ import annotations

from dataclasses import replace

from src.pipeline.capability_planner import CapabilityPlanner
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.evidence_cache import EvidenceCache
from src.pipeline.evidence_completeness import EvidenceCompleteness
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.execution_graph import (
    ExecutionGraph,
    ExecutionGraphBuilder,
    ExecutionNode,
)
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.execution_runtime import ExecutionRuntime, RuntimeMetrics
from src.pipeline.intent_resolver import IntentResolver
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.parameter_binder import MissingParameterError, ParameterBindingError
from src.pipeline.request_frame import RequestFrame
from src.pipeline.routing_decision import (
    EvidenceStatus,
    RoutingClarificationError,
    RoutingDecision,
    RoutingStatus,
)
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
        from src.pipeline.normalizer import Normalizer
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

        if state.routing_status is RoutingStatus.CLARIFICATION_REQUIRED:
            frame = state.request_frame
            labels = tuple(
                str(getattr(candidate, "label", candidate))
                for candidate in getattr(frame, "concept_candidates", ())[:3]
            )
            raise RoutingClarificationError(
                RoutingDecision(
                    status=RoutingStatus.CLARIFICATION_REQUIRED,
                    request_frame=frame,
                    reason="ambiguous request semantics",
                    missing_field=(frame.ambiguity[0] if frame.ambiguity else "concept"),
                    candidates=labels,
                )
            )

        # Phase 6: Select tool
        tool_selector = ToolSelector()
        semantic = state.request_frame
        state = state.apply(
            {
                "selected_tool": tool_selector.select(
                    semantic.raw_request, semantic.concept
                )
            }
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
        semantic = state.request_frame
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
            request_frame=state.request_frame,
            semantic_request=state.request_frame,
            intent_candidates=state.intent_candidates,
            intent_score=state.intent_score,
            intent_margin=state.intent_margin,
            target_candidates=state.target_candidates,
            target_score=state.target_score,
            target_margin=state.target_margin,
            routing_status=state.routing_status,
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

        target = state.target or "localhost"
        graph, cached_evidence = self._without_cached_nodes(graph, target)

        # Execute graph
        if graph.nodes:
            required_evidence = {
                ref.evidence_name for ref in state.capability_references if ref.required
            }
            required_evidence.difference_update(
                package.evidence_name for package in cached_evidence
            )
            extracted_params = state.extracted_params
            results, metrics = self._runtime.execute(
                graph,
                target=target,
                required_evidence_names=required_evidence,
                extracted_params=extracted_params,
                timeframe=getattr(state.request_frame, "timeframe", None),
            )
        else:
            results, metrics = {}, RuntimeMetrics()

        # Merge evidence
        self._evidence_merge.merge(temp_req, results)
        temp_req.evidence = cached_evidence + temp_req.evidence
        state = state.apply({"evidence": tuple(temp_req.evidence)})

        # Completeness check
        self._evidence_completeness.check(temp_req)
        evidence_status = self._evidence_status(temp_req)
        state = state.apply(
            {
                "evidence_complete": temp_req.evidence_complete,
                "missing_evidence": temp_req.missing_evidence,
                "evidence_status": evidence_status,
            }
        )

        # Cache evidence (with target for cross-machine isolation).
        if self._evidence_cache is not None:
            _target = state.target or "localhost"
            for pkg in temp_req.evidence:
                if pkg.valid_for_requirements:
                    self._evidence_cache.put(_target, pkg.evidence_name, pkg)

        # Attach metrics
        metrics.evidence_complete = temp_req.evidence_complete
        state = state.apply({"runtime_metrics": metrics})

        return state

    def execute(self, user_request: str | RequestFrame) -> InvestigationRequest:
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
        semantic = (
            user_request
            if isinstance(user_request, RequestFrame)
            else normalizer.normalize(user_request)
        )
        # Stage 1: Resolve intent from the same canonical frame.
        request = self._intent_resolver.resolve(semantic)
        if request.routing_status is RoutingStatus.CLARIFICATION_REQUIRED:
            labels = tuple(
                str(getattr(candidate, "label", candidate))
                for candidate in semantic.concept_candidates[:3]
            )
            raise RoutingClarificationError(
                RoutingDecision(
                    status=RoutingStatus.CLARIFICATION_REQUIRED,
                    request_frame=semantic,
                    reason="ambiguous request semantics",
                    missing_field=(
                        semantic.ambiguity[0] if semantic.ambiguity else "concept"
                    ),
                    candidates=labels,
                )
            )

        # Phase 6: Select tool for evidence collection.
        from src.pipeline.tool_selector import ToolSelector

        tool_selector = ToolSelector()
        request.selected_tool = tool_selector.select(
            semantic.raw_request, semantic.concept
        )

        # Stage 2: Resolve target.
        self._target_resolver.resolve(request)

        # Stage 3: Plan one or more bounded semantic subrequests and merge the
        # resulting capability set deterministically.
        self._plan_request(request, semantic)

        self._execution_planner.plan(request)

        # Stage 4: Build execution graph.
        if request.execution_plan is not None:
            graph = self._graph_builder.build(request.execution_plan)
        else:
            graph = ExecutionGraph()
        request.execution_graph = graph

        target = request.target or "localhost"
        timeframe = getattr(request.request_frame, "timeframe", None)
        try:
            self._runtime.validate_graph_parameters(
                graph,
                target=target,
                extracted_params=request.extracted_params,
                timeframe=timeframe,
            )
        except MissingParameterError as exc:
            field = self._clarification_field(exc.parameter)
            raise RoutingClarificationError(
                RoutingDecision(
                    status=RoutingStatus.CLARIFICATION_REQUIRED,
                    request_frame=request.request_frame or semantic,
                    reason=str(exc),
                    missing_field=field,
                )
            ) from exc
        except ParameterBindingError as exc:
            raise RoutingClarificationError(
                RoutingDecision(
                    status=RoutingStatus.CLARIFICATION_REQUIRED,
                    request_frame=request.request_frame or semantic,
                    reason=str(exc),
                    missing_field=self._clarification_field(exc.parameter),
                )
            ) from exc
        graph, cached_evidence = self._without_cached_nodes(graph, target)

        # Stage 5: Execute the graph through the runtime.
        if graph.nodes:
            required_evidence = {
                ref.evidence_name
                for ref in request.capability_references
                if ref.required
            }
            required_evidence.difference_update(
                package.evidence_name for package in cached_evidence
            )
            # Phase 6: Pass extracted params to runtime for filtered evidence collection.
            extracted_params = getattr(request, "extracted_params", None)
            results, metrics = self._runtime.execute(
                graph,
                target=target,
                required_evidence_names=required_evidence,
                extracted_params=extracted_params,
                timeframe=timeframe,
                bound_params_out=request.bound_params,
            )
        else:
            results, metrics = {}, RuntimeMetrics()

        # Stage 6: Merge evidence + completeness.
        self._merge(request, results)
        request.evidence = cached_evidence + request.evidence
        self._evidence_completeness.check(request)
        request.evidence_status = self._evidence_status(request)

        # Phase 6: Cache collected evidence for reuse across turns.
        if self._evidence_cache is not None:
            _target = request.target or "localhost"
            for pkg in request.evidence:
                if pkg.valid_for_requirements:
                    self._evidence_cache.put(_target, pkg.evidence_name, pkg)

        # Attach metrics to the request for observability.
        metrics.evidence_complete = request.evidence_complete
        request.runtime_metrics = metrics

        return request

    @staticmethod
    def _clarification_field(parameter: str) -> str:
        if parameter in {"name", "query", "service_name"}:
            return "service"
        if parameter in {"since", "until", "time_range"}:
            return "timeframe"
        if parameter == "path":
            return "path"
        if parameter == "target":
            return "target"
        return parameter

    def _plan_request(
        self,
        request: InvestigationRequest,
        semantic: RequestFrame,
    ) -> None:
        subframes = semantic.subframes or (semantic,)
        request.subrequests = tuple(subframes)
        if len(subframes) == 1:
            self._evidence_planner.plan(request)
            self._capability_resolver.resolve(request)
            self._filter_capabilities(request, subframes[0])
            return

        required_by_name: dict[str, EvidenceRequirement] = {}
        optional_by_name: dict[str, EvidenceRequirement] = {}
        references_by_name: dict[str, CapabilityReference] = {}
        for subframe in subframes:
            subrequest = self._intent_resolver.resolve(subframe)
            self._evidence_planner.plan(subrequest)
            self._capability_resolver.resolve(subrequest)
            self._filter_capabilities(subrequest, subframe)
            for requirement in subrequest.required_evidence:
                required_by_name.setdefault(requirement.name, requirement)
                optional_by_name.pop(requirement.name, None)
            for requirement in subrequest.optional_evidence:
                if requirement.name not in required_by_name:
                    optional_by_name.setdefault(requirement.name, requirement)
            for reference in subrequest.capability_references:
                current = references_by_name.get(reference.name)
                if current is None:
                    references_by_name[reference.name] = reference
                elif reference.required and not current.required:
                    references_by_name[reference.name] = replace(
                        current, required=True
                    )

        request.required_evidence = list(required_by_name.values())
        request.optional_evidence = list(optional_by_name.values())
        request.capability_references = list(references_by_name.values())

    def _filter_capabilities(
        self,
        request: InvestigationRequest,
        semantic: RequestFrame,
    ) -> None:
        if semantic.confidence < 0.4:
            return
        planned_names = set(self._capability_planner.plan(semantic))
        if not planned_names:
            return
        filtered = [
            ref
            for ref in request.capability_references
            if ref.evidence_name in planned_names
        ]
        if filtered:
            request.capability_references = filtered

    @staticmethod
    def _evidence_status(request: InvestigationRequest) -> EvidenceStatus:
        if request.evidence_complete:
            return EvidenceStatus.SUFFICIENT
        if any(package.valid_for_requirements for package in request.evidence):
            return EvidenceStatus.PARTIAL
        return EvidenceStatus.UNAVAILABLE

    def _without_cached_nodes(
        self,
        graph: ExecutionGraph,
        target: str,
    ) -> tuple[ExecutionGraph, list[EvidencePackage]]:
        if self._evidence_cache is None or not graph.nodes:
            return graph, []

        cached_by_name: dict[str, EvidencePackage] = {}
        cached_capabilities: set[str] = set()
        remaining_nodes: list[ExecutionNode] = []
        for node in graph.nodes:
            evidence_name = node.execution_step.capability.evidence_name
            cached = self._evidence_cache.get(target, evidence_name)
            if (
                isinstance(cached, EvidencePackage)
                and cached.valid_for_requirements
            ):
                cached_by_name.setdefault(evidence_name, cached)
                cached_capabilities.add(node.execution_step.capability.name)
            else:
                remaining_nodes.append(node)

        # A cached node counts as completed. Remove it from the runtime graph and
        # also remove its dependency edge from downstream nodes; otherwise the
        # runtime cannot observe that completion and may force nodes out of order.
        if cached_capabilities:
            remaining_nodes = [
                ExecutionNode(
                    execution_step=node.execution_step,
                    depends_on=tuple(
                        dependency
                        for dependency in node.depends_on
                        if dependency not in cached_capabilities
                    ),
                )
                for node in remaining_nodes
            ]

        return ExecutionGraph(nodes=tuple(remaining_nodes)), list(
            cached_by_name.values()
        )

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
