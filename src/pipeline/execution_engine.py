from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

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
from src.pipeline.source_constraints import (
    SourceConstraintUnavailableError,
    allowed_source_names,
)
from src.pipeline.target_resolver import TargetResolver
from src.pipeline.threshold_evaluator import ThresholdEvaluator
from src.shared.config_schema import (
    FeatureFlagsConfig,
    RuleConfigError,
    load_rule_configs,
)
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

    Never performs reasoning or assessment.
    """

    @property
    def knowledge_tool(self) -> KnowledgeTool:
        return self._knowledge_tool

    @property
    def target_resolver(self) -> TargetResolver:
        return self._target_resolver

    @property
    def execution_budget_config(self) -> ExecutionBudgetConfig:
        return self._budget_config

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
        require_configured_rules: bool = True,
        feature_flags: FeatureFlagsConfig | None = None,
        source_constraints_enabled: bool = True,
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
        if not atomic_rules and require_configured_rules:
            # Fail startup rather than silently falling back to
            # ThresholdEvaluator's hardcoded DEFAULT_ATOMIC_RULES — a
            # missing/empty config/rules/ directory at deploy time must
            # be a loud, immediate error, not an undetected downgrade to
            # unreviewed thresholds (DR1-610). Callers that genuinely
            # want the permissive fallback (e.g. lightweight scripts,
            # ad-hoc tooling) can opt in explicitly.
            raise RuleConfigError(
                "No atomic reasoning rules were loaded from config/rules/. "
                "This engine refuses to silently fall back to hardcoded "
                "DEFAULT_ATOMIC_RULES for production use — rules must be "
                "versioned, owned, and reviewed config (see "
                "src/shared/config_schema.py::load_rule_configs). If this "
                "is intentional (e.g. a script that doesn't need "
                "reasoning rules), pass require_configured_rules=False."
            )
        self._threshold_evaluator = ThresholdEvaluator(atomic_rules or None)
        self._correlation = EvidenceCorrelation(composite_rules)
        self._evidence_expander = EvidenceExpander()
        self._health_aggregator = HealthAggregator()
        self._budget_config = execution_budget_config or ExecutionBudgetConfig()
        self._composite_rules_enabled = (
            True if feature_flags is None else feature_flags.composite_rules
        )
        self._source_constraints_enabled = source_constraints_enabled

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

        # Stage 2: Resolve target.
        self._target_resolver.resolve(request)

        target = request.target or "localhost"
        self._assert_execution_target(request, target)
        allowed_sources = (
            allowed_source_names(
                self._knowledge_tool,
                semantic.source_constraints,
                target=target,
            )
            if self._source_constraints_enabled
            else None
        )

        # Stage 3: Plan one or more bounded semantic subrequests and merge the
        # resulting capability set deterministically.
        self._plan_request(request, semantic)
        self._validate_source_capability_coverage(request, allowed_sources)

        self._execution_planner.plan(request)

        # Stage 4: Build execution graph.
        if request.execution_plan is not None:
            graph = self._graph_builder.build(request.execution_plan)
        else:
            graph = ExecutionGraph()
        graph = self._expand_multi_source_graph(
            graph,
            request,
            allowed_sources=allowed_sources,
        )
        request.execution_graph = graph

        timeframe = getattr(request.request_frame, "timeframe", None)
        try:
            self._runtime.validate_graph_parameters(
                graph,
                target=target,
                extracted_params=request.extracted_params,
                timeframe=timeframe,
                allowed_sources=allowed_sources,
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
            allowed_sources=allowed_sources,
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
            # A comparison must execute every explicit source.  Runtime's
            # normal early-completion optimization keys only on evidence name
            # and would otherwise stop after the first source succeeds.
            if allowed_sources is not None and len(allowed_sources) > 1:
                required_evidence = set()
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
                budget=budget,
                allowed_sources=allowed_sources,
            )
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
            allowed_sources=allowed_sources,
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

    def _assert_execution_target(
        self,
        request: InvestigationRequest,
        execution_target: str,
    ) -> None:
        """Fail closed if planning would execute on an unproven target.

        TargetResolver is the sole authority for explicit targets.  This
        check sits immediately after resolution and before planning/runtime
        dispatch so a later fallback cannot turn an unresolved explicit host
        into localhost evidence.
        """

        frame = request.request_frame
        if isinstance(frame, RequestFrame):
            if frame.target_raw is not None and frame.target_resolved is None:
                raise ValueError(
                    "Explicit target was not resolved; environment execution is denied."
                )
            if (
                frame.target_resolved is not None
                and frame.target_resolved != execution_target
            ):
                raise ValueError(
                    "Execution target differs from the resolved request target."
                )
            if execution_target not in self._knowledge_tool.source_names():
                raise ValueError(
                    f"Resolved execution target '{execution_target}' is not registered."
                )

    def _apply_reasoning(self, request: InvestigationRequest):
        """Attach canonical atomic/composite findings and health summary."""

        request.fact_set = self._threshold_evaluator.derive_facts(request.fact_set)
        request.atomic_findings = self._threshold_evaluator.evaluate_fact_set(
            request.fact_set
        )
        evaluations = (
            self._correlation.evaluate_facts(request.fact_set)
            if self._composite_rules_enabled
            else ()
        )
        composite_findings = tuple(item.finding for item in evaluations)
        request.findings = tuple(request.atomic_findings) + composite_findings
        request.health_summary = self._health_aggregator.aggregate(
            request.fact_set,
            request.findings,
            request.evidence_completeness,
            default_target=request.target or "localhost",
        )
        return evaluations

    def _validate_source_capability_coverage(
        self,
        request: InvestigationRequest,
        allowed_sources: frozenset[str] | None,
    ) -> None:
        """Fail closed when a hard source cannot serve the planned evidence.

        Discovering a configured Grafana/Zabbix endpoint is not enough: if it
        does not expose a route for the required capability, collecting Linux
        evidence would be a silent source broadening.  A reviewed multi-source
        allow-set remains valid when at least one constrained source can serve
        each capability; individual runtime receipts keep their own source.
        """

        if allowed_sources is None:
            return
        unavailable: list[str] = []
        for reference in request.capability_references:
            if not reference.required:
                continue
            routes = self._runtime.router.resolve_all_with_metadata(
                reference.name,
                request.extracted_params,
                allowed_sources=allowed_sources,
            )
            routed_sources = {route[0] for route, _ in routes}
            if len(allowed_sources) == 1:
                if not routes:
                    unavailable.append(reference.name)
            elif routed_sources != set(allowed_sources):
                missing = ", ".join(sorted(set(allowed_sources) - routed_sources))
                unavailable.append(f"{reference.name} (missing {missing})")
        if unavailable:
            labels = ", ".join(unavailable[:3])
            sources = ", ".join(sorted(allowed_sources))
            raise SourceConstraintUnavailableError(
                f"Configured constrained source(s) [{sources}] cannot provide: {labels}."
            )

    def _expand_multi_source_graph(
        self,
        graph: ExecutionGraph,
        request: InvestigationRequest,
        *,
        allowed_sources: frozenset[str] | None,
    ) -> ExecutionGraph:
        """Duplicate reviewed nodes only for an explicit multi-source set.

        Node names receive a source suffix for runtime/result-map uniqueness,
        while their evidence name remains unchanged.  Runtime pins each clone
        to its named source; EvidenceMerge maps the suffix back to the original
        evidence contract and preserves separate receipt provenance.
        """

        if allowed_sources is None or len(allowed_sources) < 2 or not graph.nodes:
            return graph
        nodes: list[ExecutionNode] = []
        for node in graph.nodes:
            step = node.execution_step
            base_name = step.capability.name
            routes = self._runtime.router.resolve_all_with_metadata(
                base_name,
                request.extracted_params,
                allowed_sources=allowed_sources,
            )
            for (source, _resource), _metadata in routes:
                clone_name = f"{base_name}::{source}"
                metadata = dict(step.metadata)
                metadata.update(
                    {
                        "base_capability": base_name,
                        "forced_source": source,
                    }
                )
                nodes.append(
                    ExecutionNode(
                        execution_step=ExecutionStep(
                            capability=replace(step.capability, name=clone_name),
                            step_id=(
                                f"{step.step_id}::{source}"
                                if step.step_id
                                else clone_name
                            ),
                            metadata=MappingProxyType(metadata),
                        ),
                        depends_on=tuple(
                            f"{dependency}::{source}"
                            for dependency in node.depends_on
                        ),
                    )
                )
        return ExecutionGraph(nodes=tuple(nodes))

    def _expand_evidence(
        self,
        request: InvestigationRequest,
        *,
        budget: ExecutionBudget,
        target: str,
        timeframe: object,
        metrics: RuntimeMetrics,
        allowed_sources: frozenset[str] | None,
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
            budget=budget,
            allowed_sources=allowed_sources,
        )
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
        """Fit the primary plan inside hard capability/cost limits.

        A node whose prerequisite was cut for budget reasons must also be
        dropped — otherwise stripping the dangling ``depends_on`` edge
        turns it into an independent node that the runtime will happily
        execute without ever having run its prerequisite. After the
        greedy budget selection, this computes the dependency closure and
        removes any node (transitively) missing a prerequisite, so every
        node kept in the returned graph still has every dependency it
        declared, fully satisfied within the same bounded graph.
        """

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

        selected_by_name = {
            node.execution_step.capability.name: node for node in selected
        }

        # Dependency closure: repeatedly drop any node whose depends_on
        # references a capability that isn't (or is no longer) selected,
        # until the selection stops shrinking.
        changed = True
        while changed:
            changed = False
            for name, node in list(selected_by_name.items()):
                if any(dep not in selected_by_name for dep in node.depends_on):
                    del selected_by_name[name]
                    changed = True

        bounded = tuple(
            node
            for node in graph.nodes
            if node.execution_step.capability.name in selected_by_name
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
        allowed_sources: frozenset[str] | None = None,
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
                    allowed_sources=allowed_sources,
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
        # Runtime receipts, not lexical tool-selection hints, own provenance.
        self._evidence_merge.merge(request, results)
