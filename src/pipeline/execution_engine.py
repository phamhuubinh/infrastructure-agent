from __future__ import annotations

from dataclasses import replace

from src.pipeline.capability_planner import CapabilityPlanner
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_resolver import CapabilityResolver
from src.pipeline.evidence_cache import EvidenceCache
from src.pipeline.evidence_completeness import (
    EvidenceCompleteness,
    EvidenceCompletenessResult,
    RequirementStatus,
)
from src.pipeline.evidence_correlation import EvidenceCorrelation
from src.pipeline.evidence_expander import EvidenceExpander, ExpansionCandidate
from src.pipeline.evidence_merge import EvidenceMerge
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.execution_budget import (
    BudgetStopReason,
    ExecutionBudget,
    ExecutionBudgetConfig,
)
from src.pipeline.execution_graph import (
    ExecutionGraph,
    ExecutionGraphBuilder,
    ExecutionNode,
)
from src.pipeline.execution_plan import ExecutionStep
from src.pipeline.execution_planner import ExecutionPlanner
from src.pipeline.execution_runtime import ExecutionRuntime, RuntimeMetrics
from src.pipeline.health_aggregator import HealthAggregator
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
from src.pipeline.threshold_evaluator import ThresholdEvaluator
from src.shared.config_schema import load_rule_configs
from src.shared.execution.tool_result import ToolResult
from src.tool.errors import CapabilityErrorCategory
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
        execution_budget_config: ExecutionBudgetConfig | None = None,
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
        rule_configs = load_rule_configs()
        atomic_rules = tuple(
            rule.to_domain()
            for config in rule_configs
            for rule in config.atomic_rules
        )
        composite_rules = tuple(
            rule.to_domain()
            for config in rule_configs
            for rule in config.composite_rules
        )
        self._threshold_evaluator = ThresholdEvaluator(atomic_rules or None)
        self._correlation = EvidenceCorrelation(composite_rules)
        self._evidence_expander = EvidenceExpander()
        self._health_aggregator = HealthAggregator()
        self._budget_config = execution_budget_config or ExecutionBudgetConfig()

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
            extracted_params=state.extracted_params,
            selected_tool=state.selected_tool,
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
        graph, cached_evidence = self._without_cached_nodes(
            graph,
            target,
            extracted_params=state.extracted_params,
            timeframe=getattr(state.request_frame, "timeframe", None),
            requirements=state.required_evidence,
        )
        budget = ExecutionBudget(self._budget_config)
        temp_req.execution_budget = budget
        graph = self._bounded_graph(graph, budget)

        # Execute graph
        if graph.nodes:
            budget.start_round(
                len(graph.nodes),
                sum(
                    node.execution_step.capability.estimated_cost
                    for node in graph.nodes
                ),
            )
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
                overall_timeout=budget.remaining_duration,
            )
            budget.capabilities += metrics.recovery_attempts
        else:
            results, metrics = {}, RuntimeMetrics()

        # Merge evidence
        self._evidence_merge.merge(temp_req, results)
        temp_req.evidence = cached_evidence + temp_req.evidence
        self._evidence_merge.rebuild_fact_set(temp_req)
        state = state.apply(
            {
                "evidence": tuple(temp_req.evidence),
                "fact_set": temp_req.fact_set,
                "contradictions": temp_req.contradictions,
            }
        )

        # Completeness check
        self._evidence_completeness.check(temp_req)
        self._apply_reasoning(temp_req)
        self._expand_evidence(
            temp_req,
            budget=budget,
            target=target,
            timeframe=getattr(state.request_frame, "timeframe", None),
            metrics=metrics,
        )
        evidence_status = self._evidence_status(temp_req)
        state = state.apply(
            {
                "evidence": tuple(temp_req.evidence),
                "fact_set": temp_req.fact_set,
                "contradictions": temp_req.contradictions,
                "evidence_complete": temp_req.evidence_complete,
                "missing_evidence": temp_req.missing_evidence,
                "evidence_status": evidence_status,
                "evidence_completeness": temp_req.evidence_completeness,
                "atomic_findings": temp_req.atomic_findings,
                "findings": temp_req.findings,
                "health_summary": temp_req.health_summary,
                "evidence_expansion": temp_req.evidence_expansion,
                "execution_budget": budget,
            }
        )

        # Cache evidence (with target for cross-machine isolation).
        if self._evidence_cache is not None:
            _target = state.target or "localhost"
            for pkg in temp_req.evidence:
                if pkg.valid_for_requirements:
                    self._evidence_cache.put(
                        _target,
                        pkg.evidence_name,
                        pkg,
                        capability=pkg.capability_name,
                        params=pkg.parameters,
                        timeframe=pkg.timeframe,
                        schema_version=pkg.schema_version,
                    )

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
        graph, cached_evidence = self._without_cached_nodes(
            graph,
            target,
            extracted_params=request.extracted_params,
            timeframe=timeframe,
            requirements=request.required_evidence,
        )

        budget = ExecutionBudget(self._budget_config)
        request.execution_budget = budget
        graph = self._bounded_graph(graph, budget)

        # Stage 5: Execute the graph through the runtime.
        if graph.nodes:
            budget.start_round(
                len(graph.nodes),
                sum(
                    node.execution_step.capability.estimated_cost
                    for node in graph.nodes
                ),
            )
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
                overall_timeout=budget.remaining_duration,
            )
            budget.capabilities += metrics.recovery_attempts
        else:
            results, metrics = {}, RuntimeMetrics()

        # Stage 6: Merge evidence + completeness.
        self._merge(request, results)
        request.evidence = cached_evidence + request.evidence
        self._evidence_merge.rebuild_fact_set(request)
        self._evidence_completeness.check(request)
        self._apply_reasoning(request)
        self._expand_evidence(
            request,
            budget=budget,
            target=target,
            timeframe=timeframe,
            metrics=metrics,
        )
        request.evidence_status = self._evidence_status(request)

        # Phase 6: Cache collected evidence for reuse across turns.
        if self._evidence_cache is not None:
            _target = request.target or "localhost"
            for pkg in request.evidence:
                if pkg.valid_for_requirements:
                    self._evidence_cache.put(
                        _target,
                        pkg.evidence_name,
                        pkg,
                        capability=pkg.capability_name,
                        params=pkg.parameters,
                        timeframe=pkg.timeframe,
                        schema_version=pkg.schema_version,
                    )

        # Attach metrics to the request for observability.
        metrics.evidence_complete = request.evidence_complete
        request.runtime_metrics = metrics

        return request

    def _apply_reasoning(self, request: InvestigationRequest):
        """Attach canonical atomic/composite findings and health summary."""

        request.fact_set = self._threshold_evaluator.derive_facts(request.fact_set)
        request.atomic_findings = self._threshold_evaluator.evaluate_fact_set(
            request.fact_set
        )
        evaluations = self._correlation.evaluate_facts(request.fact_set)
        composite_findings = tuple(item.finding for item in evaluations)
        request.findings = tuple(request.atomic_findings) + composite_findings
        request.health_summary = self._health_aggregator.aggregate(
            request.fact_set,
            request.findings,
            request.evidence_completeness,
            default_target=request.target or "localhost",
        )
        return evaluations

    def _expand_evidence(
        self,
        request: InvestigationRequest,
        *,
        budget: ExecutionBudget,
        target: str,
        timeframe: object,
        metrics: RuntimeMetrics,
    ) -> None:
        """Run at most one weighted expansion round under the shared budget."""

        if request.evidence_complete:
            budget.stop(evidence_sufficient=True)
            return
        transport_failed = any(
            package.capability_error is not None
            and package.capability_error.category is CapabilityErrorCategory.TRANSPORT
            for package in request.evidence
        )
        if transport_failed:
            budget.stop(transport_failed=True)
            return

        evaluations = self._correlation.evaluate_facts(request.fact_set)
        planned = {reference.name for reference in request.capability_references}
        candidates = self._evidence_expander.select(
            evaluations,
            already_planned=planned,
        )
        if not candidates:
            budget.stop(recoverable_path=False)
            return
        estimated_cost = sum(candidate.estimated_cost for candidate in candidates)
        if not budget.start_round(len(candidates), estimated_cost):
            return

        references = tuple(self._expansion_reference(item) for item in candidates)
        request.capability_references.extend(references)
        graph = ExecutionGraph(
            nodes=tuple(
                ExecutionNode(execution_step=ExecutionStep(capability=reference))
                for reference in references
            )
        )
        results, expansion_metrics = self._runtime.execute(
            graph,
            target=target,
            overall_timeout=budget.remaining_duration,
            required_evidence_names={item.evidence_name for item in candidates},
            extracted_params=request.extracted_params,
            timeframe=timeframe,
            bound_params_out=request.bound_params,
        )
        budget.capabilities += expansion_metrics.recovery_attempts
        previous_evidence = list(request.evidence)
        self._merge(request, results)
        request.evidence = previous_evidence + request.evidence
        self._evidence_merge.rebuild_fact_set(request)
        self._evidence_completeness.check(request)
        request.evidence_expansion = candidates
        self._apply_reasoning(request)
        self._merge_runtime_metrics(metrics, expansion_metrics, candidates)
        budget.stop(
            evidence_sufficient=request.evidence_complete,
            recoverable_path=False,
            transport_failed=any(
                package.capability_error is not None
                and package.capability_error.category
                is CapabilityErrorCategory.TRANSPORT
                for package in request.evidence
            ),
        )

    @staticmethod
    def _expansion_reference(candidate: ExpansionCandidate) -> CapabilityReference:
        return CapabilityReference(
            name=candidate.capability,
            evidence_name=candidate.evidence_name,
            required=False,
            estimated_cost=candidate.estimated_cost,
        )

    @staticmethod
    def _merge_runtime_metrics(
        metrics: RuntimeMetrics,
        extra: RuntimeMetrics,
        candidates: tuple[ExpansionCandidate, ...],
    ) -> None:
        old_total = metrics.total_nodes
        new_total = old_total + extra.total_nodes
        metrics.execution_duration += extra.execution_duration
        metrics.total_nodes = new_total
        metrics.successful_nodes += extra.successful_nodes
        metrics.failed_nodes += extra.failed_nodes
        if new_total:
            metrics.parallel_ratio = (
                metrics.parallel_ratio * old_total
                + extra.parallel_ratio * extra.total_nodes
            ) / new_total
        metrics.tool_calls += extra.tool_calls
        metrics.timed_out = metrics.timed_out or extra.timed_out
        metrics.security_inspections_total += extra.security_inspections_total
        metrics.security_inspections_passed += extra.security_inspections_passed
        metrics.security_inspections_blocked += extra.security_inspections_blocked
        metrics.recovery_attempts += extra.recovery_attempts
        metrics.recovery_successes += extra.recovery_successes
        metrics.expansion_rounds += 1
        metrics.expanded_capabilities = tuple(
            dict.fromkeys(
                metrics.expanded_capabilities
                + tuple(candidate.capability for candidate in candidates)
            )
        )

    @staticmethod
    def _bounded_graph(
        graph: ExecutionGraph,
        budget: ExecutionBudget,
    ) -> ExecutionGraph:
        """Fit the primary plan inside hard capability/cost limits."""

        selected: list[ExecutionNode] = []
        cost = 0.0
        for node in graph.nodes:
            node_cost = node.execution_step.capability.estimated_cost
            if len(selected) >= budget.config.max_capabilities:
                break
            if cost + node_cost > budget.config.max_estimated_cost:
                continue
            selected.append(node)
            cost += node_cost
        selected_names = {
            node.execution_step.capability.name for node in selected
        }
        bounded = tuple(
            ExecutionNode(
                execution_step=node.execution_step,
                depends_on=tuple(
                    dependency
                    for dependency in node.depends_on
                    if dependency in selected_names
                ),
            )
            for node in selected
        )
        if len(bounded) < len(graph.nodes):
            budget.stop_reason = BudgetStopReason.BUDGET_EXHAUSTED
        return ExecutionGraph(nodes=bounded)

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
        if request.contradictions:
            return EvidenceStatus.CONTRADICTORY
        if any(package.stale for package in request.evidence):
            return EvidenceStatus.STALE
        completeness = request.evidence_completeness
        if isinstance(completeness, EvidenceCompletenessResult):
            if completeness.statuses(RequirementStatus.CONTRADICTORY):
                return EvidenceStatus.CONTRADICTORY
            if completeness.statuses(RequirementStatus.STALE):
                return EvidenceStatus.STALE
        if request.evidence_complete:
            return EvidenceStatus.SUFFICIENT
        if any(package.valid_for_requirements for package in request.evidence):
            return EvidenceStatus.PARTIAL
        return EvidenceStatus.UNAVAILABLE

    def _without_cached_nodes(
        self,
        graph: ExecutionGraph,
        target: str,
        *,
        extracted_params: object = None,
        timeframe: object = None,
        requirements: object = (),
    ) -> tuple[ExecutionGraph, list[EvidencePackage]]:
        if self._evidence_cache is None or not graph.nodes:
            return graph, []

        cached_by_name: dict[str, EvidencePackage] = {}
        cached_capabilities: set[str] = set()
        remaining_nodes: list[ExecutionNode] = []
        for node in graph.nodes:
            evidence_name = node.execution_step.capability.evidence_name
            allow_stale = any(
                getattr(requirement, "name", None) == evidence_name
                and bool(getattr(requirement, "allow_stale", False))
                for requirement in (
                    requirements if isinstance(requirements, (list, tuple)) else ()
                )
            )
            try:
                params = self._runtime.cache_parameters(
                    node,
                    target=target,
                    extracted_params=extracted_params,
                    timeframe=timeframe,
                )
            except ParameterBindingError:
                params = ()
            cached = self._evidence_cache.get(
                target,
                evidence_name,
                capability=node.execution_step.capability.name,
                params=params,
                timeframe=timeframe,
                schema_version="1",
                allow_stale=allow_stale,
            )
            if cached is None and not params and timeframe is None:
                # Read-only migration path for entries written by the former
                # target+evidence-name cache contract.
                cached = self._evidence_cache.get(
                    target,
                    evidence_name,
                    allow_stale=allow_stale,
                )
            if (
                isinstance(cached, EvidencePackage)
                and (
                    cached.valid_for_requirements
                    or (allow_stale and cached.stale)
                )
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
