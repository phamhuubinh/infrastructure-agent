from __future__ import annotations

import concurrent.futures
import threading
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, replace

from src.pipeline.capability_recovery import (
    CapabilityRecovery,
    CapabilityRecoverySpec,
)
from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_router import CapabilityRouter
from src.pipeline.execution_budget import ExecutionBudget
from src.pipeline.execution_graph import ExecutionGraph, ExecutionNode
from src.pipeline.execution_plan import ExecutionStep
from src.pipeline.parameter_binder import ParameterBinder, ParameterBindingError
from src.pipeline.retry import RetryExecutor, RetryPolicy, is_recoverable_result
from src.shared.execution.tool_result import ToolResult
from src.shared.logger import warning as _warning
from src.tool.capability_result import CapabilityStatus
from src.tool.errors import internal_error
from src.tool.knowledge_tool import KnowledgeTool


class GraphValidationError(ValueError):
    """Raised when an ExecutionGraph references a dependency that does not
    exist among its own nodes. Raised before any node executes so a
    broken graph fails fast instead of silently force-executing nodes
    whose prerequisites can never be satisfied."""

    def __init__(self, errors: tuple[str, ...]) -> None:
        self.errors = errors
        super().__init__(
            "Execution graph has unresolvable dependencies: " + "; ".join(errors)
        )


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
    timed_out: bool = False
    early_completed: bool = False
    security_inspections_total: int = 0
    security_inspections_passed: int = 0
    security_inspections_blocked: int = 0
    recovery_attempts: int = 0
    recovery_successes: int = 0
    blocked_by_dependency: int = 0
    expansion_rounds: int = 0
    expanded_capabilities: tuple[str, ...] = ()


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
        retry_executor: RetryExecutor | None = None,
    ) -> None:
        self._knowledge_tool = knowledge_tool
        self._router = router or CapabilityRouter()
        self._retry = retry_executor or RetryExecutor(
            RetryPolicy(max_attempts=3),
        )
        self._evidence_name_by_cap: dict[str, str] = {}
        self._parameter_binder = ParameterBinder()

    @property
    def router(self) -> CapabilityRouter:
        """Access the router for route building."""
        return self._router

    def execute(
        self,
        graph: ExecutionGraph,
        target: str = "localhost",
        overall_timeout: float = 120.0,
        required_evidence_names: set[str] | None = None,
        extracted_params: object = None,
        timeframe: object = None,
        bound_params_out: dict[str, dict[str, object]] | None = None,
        budget: ExecutionBudget | None = None,
        allowed_sources: frozenset[str] | None = None,
    ) -> tuple[dict[str, ToolResult], RuntimeMetrics]:
        """Execute all nodes in the graph and return collected evidence.

        Nodes are executed respecting dependency order.
        Independent nodes may execute in parallel.
        Failed nodes are recorded but do not terminate execution.

        If `overall_timeout` is exceeded, partial results are returned
        and the timeout is recorded in metrics. A SIGALRM-based timeout
        interrupts blocking tool calls without killing the process.

        When `required_evidence_names` is provided, execution stops early
        once all required evidence has been successfully collected.
        Remaining unexecuted nodes are skipped and the
        ``early_completed`` metric is set to ``True``.

        Returns both results and runtime metrics.

        Args:
            graph: The execution graph to execute.
            target: The investigation target name.
            overall_timeout: Maximum wall-clock seconds for the entire
                             execution loop. Partial results returned on
                             timeout. 0 or negative means no timeout.
            required_evidence_names: Optional set of evidence names that
                                     must be collected. When all are
                                     satisfied, remaining nodes are
                                     skipped (early completion).
            budget: Optional shared ``ExecutionBudget``. When provided,
                    each recovery attempt reserves one capability slot
                    from this budget *before* it is dispatched, so the
                    caller's configured hard limits are never exceeded
                    mid-round — the caller no longer needs to add
                    ``metrics.recovery_attempts`` to the budget after the
                    fact. When omitted, recovery is unbounded by budget
                    (legacy behaviour), matching callers that do not pass
                    one.

        Returns:
            A tuple of (results dict, RuntimeMetrics).
        """
        metrics = RuntimeMetrics()
        t0 = _time.perf_counter()

        if not graph.nodes:
            metrics.execution_duration = _time.perf_counter() - t0
            return {}, metrics

        validation_errors = self._validate_dependencies(graph)
        if validation_errors:
            raise GraphValidationError(validation_errors)

        metrics.total_nodes = len(graph.nodes)

        completed: set[str] = set()
        results: dict[str, ToolResult] = {}
        remaining = list(graph.nodes)
        total_nodes_in_parallel = 0
        required_evidence_names = required_evidence_names or set()

        cap_to_evidence: dict[str, str] = {
            n.execution_step.capability.name: n.execution_step.capability.evidence_name
            for n in graph.nodes
        }
        collected_evidence: set[str] = set()

        _lock = threading.Lock()
        _budget_lock = threading.Lock()
        _timeout_deadline = (
            _time.perf_counter() + overall_timeout
            if overall_timeout > 0
            else float("inf")
        )

        def _record_success(cap_name: str) -> None:
            with _lock:
                completed.add(cap_name)
                ev = cap_to_evidence.get(cap_name)
                if ev:
                    collected_evidence.add(ev)

        while remaining:
            if self._check_early_completion(
                remaining,
                results,
                metrics,
                required_evidence_names,
                collected_evidence,
                _lock,
            ):
                break

            if _time.perf_counter() > _timeout_deadline:
                self._mark_remaining_as_timeout(
                    remaining, results, metrics, overall_timeout
                )
                break

            ready, remaining = self._get_ready_nodes(
                remaining, completed, results, metrics
            )
            if not ready:
                # All remaining nodes are permanently blocked by a failed
                # dependency (see _get_ready_nodes) — nothing left to run.
                break

            if len(ready) > 1:
                total_nodes_in_parallel += len(ready)

            if len(ready) == 1:
                self._execute_single_node(
                    ready[0],
                    results,
                    metrics,
                    _record_success,
                    target,
                    _timeout_deadline,
                    overall_timeout,
                    extracted_params=extracted_params,
                    timeframe=timeframe,
                    bound_params_out=bound_params_out,
                    budget=budget,
                    budget_lock=_budget_lock,
                    allowed_sources=allowed_sources,
                )
            else:
                self._execute_batch_parallel(
                    ready,
                    results,
                    metrics,
                    _record_success,
                    target,
                    _timeout_deadline,
                    overall_timeout,
                    extracted_params=extracted_params,
                    timeframe=timeframe,
                    bound_params_out=bound_params_out,
                    budget=budget,
                    budget_lock=_budget_lock,
                    allowed_sources=allowed_sources,
                )

        metrics.execution_duration = _time.perf_counter() - t0
        metrics.successful_nodes = sum(1 for r in results.values() if r.success)
        metrics.failed_nodes = sum(1 for r in results.values() if not r.success)
        if metrics.total_nodes > 0:
            metrics.parallel_ratio = total_nodes_in_parallel / metrics.total_nodes

        return results, metrics

    @staticmethod
    def _validate_dependencies(graph: ExecutionGraph) -> tuple[str, ...]:
        """Return a description of every ``depends_on`` reference that does
        not name another capability present in this graph.

        Called before execution starts so a broken/typo'd dependency graph
        fails fast with a clear error instead of silently falling into the
        force-execute fallback in ``_get_ready_nodes``.
        """
        known = {n.execution_step.capability.name for n in graph.nodes}
        errors: list[str] = []
        for node in graph.nodes:
            cap_name = node.execution_step.capability.name
            for dep in node.depends_on:
                if dep not in known:
                    errors.append(
                        f"capability '{cap_name}' depends_on unknown "
                        f"capability '{dep}' (not present in this graph)"
                    )
        return tuple(errors)

    def _check_early_completion(
        self,
        remaining: list[ExecutionNode],
        results: dict[str, ToolResult],
        metrics: RuntimeMetrics,
        required_evidence_names: set[str],
        collected_evidence: set[str],
        lock: threading.Lock,
    ) -> bool:
        """Check if all required evidence is collected and skip remaining."""
        with lock:
            if not required_evidence_names or not collected_evidence.issuperset(
                required_evidence_names
            ):
                return False
        for node in remaining:
            cap_name = node.execution_step.capability.name
            if cap_name not in results:
                results[cap_name] = ToolResult(
                    success=False,
                    error="Skipped: all required evidence already collected",
                    capability_status=CapabilityStatus.COLLECTION_FAILED,
                )
        metrics.early_completed = True
        remaining.clear()
        return True

    def _mark_remaining_as_timeout(
        self,
        remaining: list[ExecutionNode],
        results: dict[str, ToolResult],
        metrics: RuntimeMetrics,
        overall_timeout: float,
    ) -> None:
        """Mark all remaining nodes as timed out."""
        for node in remaining:
            cap_name = node.execution_step.capability.name
            if cap_name not in results:
                results[cap_name] = ToolResult(
                    success=False,
                    error=f"Execution timed out after {overall_timeout}s",
                    capability_status=CapabilityStatus.COLLECTION_FAILED,
                )
        metrics.timed_out = True

    def _get_ready_nodes(
        self,
        remaining: list[ExecutionNode],
        completed: set[str],
        results: dict[str, ToolResult],
        metrics: RuntimeMetrics,
    ) -> tuple[list[ExecutionNode], list[ExecutionNode]]:
        """Separate ready nodes (all deps satisfied) from remaining.

        A dependency is only satisfied when the capability it names has
        *succeeded* (see ``_record_success``, only called on
        ``result.success``). If a node's dependency already produced a
        result but failed, that node can never become ready — waiting for
        it to appear in ``completed`` would loop forever. Such nodes are
        not force-executed (a capability that needs another capability's
        output should not run without it — see DR1-101/DR1-107 failure
        contract); instead every node still blocked on a *failed*
        dependency is marked ``COLLECTION_FAILED`` with a clear
        "blocked by dependency" error and dropped from ``remaining``.
        Graph-level errors (a ``depends_on`` naming a capability absent
        from the graph entirely) are caught earlier by
        ``_validate_dependencies`` and never reach this method.
        """
        ready: list[ExecutionNode] = []
        still_remaining: list[ExecutionNode] = []
        blocked: list[ExecutionNode] = []

        for node in remaining:
            deps = node.depends_on
            unmet = [dep for dep in deps if dep not in completed]
            if not unmet:
                ready.append(node)
                continue
            failed_deps = [dep for dep in unmet if dep in results]
            if failed_deps:
                # Every unmet dependency has already run and failed (as
                # opposed to simply not having executed yet) — this node
                # can never become ready.
                blocked.append(node)
            else:
                still_remaining.append(node)

        if blocked:
            for node in blocked:
                cap_name = node.execution_step.capability.name
                failed_names = sorted(
                    dep for dep in node.depends_on if dep in results and dep not in completed
                )
                results[cap_name] = ToolResult(
                    success=False,
                    error=(
                        "Blocked by dependency: prerequisite capability "
                        f"{', '.join(failed_names)} failed"
                    ),
                    capability_status=CapabilityStatus.COLLECTION_FAILED,
                )
                metrics.blocked_by_dependency += 1

        if not ready and still_remaining and not blocked:
            # Defensive fallback: _validate_dependencies should have
            # already rejected any graph with a dependency cycle or a
            # reference to a capability outside the graph, so this
            # branch should be unreachable in practice. It exists only
            # to guarantee execute() can never hang.
            _warning(
                "execution-runtime",
                message=(
                    "no node ready and none blocked by a failed dependency "
                    "— possible dependency cycle; forcing next node"
                ),
                remaining_count=len(still_remaining),
            )
            ready = [still_remaining.pop(0)]

        return ready, still_remaining

    def _execute_single_node(
        self,
        node: ExecutionNode,
        results: dict[str, ToolResult],
        metrics: RuntimeMetrics,
        record_success: Callable[[str], None],
        target: str,
        timeout_deadline: float,
        overall_timeout: float,
        extracted_params: object = None,
        timeframe: object = None,
        bound_params_out: dict[str, dict[str, object]] | None = None,
        budget: ExecutionBudget | None = None,
        budget_lock: threading.Lock | None = None,
        allowed_sources: frozenset[str] | None = None,
    ) -> None:
        """Execute a single ready node with per-node timeout."""
        cap_name = node.execution_step.capability.name
        remaining_timeout = max(timeout_deadline - _time.perf_counter(), 0)
        if remaining_timeout <= 0:
            results[cap_name] = ToolResult(
                success=False,
                error=f"Execution timed out after {overall_timeout}s",
                capability_status=CapabilityStatus.COLLECTION_FAILED,
            )
            metrics.timed_out = True
            return

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fut = executor.submit(
                self._execute_node,
                node,
                target=target,
                extracted_params=extracted_params,
                timeframe=timeframe,
                bound_params_out=bound_params_out,
                budget=budget,
                budget_lock=budget_lock,
                allowed_sources=allowed_sources,
            )
            try:
                result = fut.result(timeout=remaining_timeout)
                metrics.tool_calls += 1
                metrics.tool_calls += len(result.recovery_attempts)
                metrics.recovery_attempts += len(result.recovery_attempts)
                metrics.recovery_successes += int(result.recovered_by is not None)
                self._record_security_metrics(metrics, result)
                results[cap_name] = result
                if result.success:
                    record_success(cap_name)
            except concurrent.futures.TimeoutError:
                metrics.timed_out = True
                results[cap_name] = ToolResult(
                    success=False,
                    error=f"Execution timed out after {overall_timeout}s",
                    capability_status=CapabilityStatus.COLLECTION_FAILED,
                )
        finally:
            executor.shutdown(wait=False)

    def _execute_batch_parallel(
        self,
        ready: list[ExecutionNode],
        results: dict[str, ToolResult],
        metrics: RuntimeMetrics,
        record_success: Callable[[str], None],
        target: str,
        timeout_deadline: float,
        overall_timeout: float,
        extracted_params: object = None,
        timeframe: object = None,
        bound_params_out: dict[str, dict[str, object]] | None = None,
        budget: ExecutionBudget | None = None,
        budget_lock: threading.Lock | None = None,
        allowed_sources: frozenset[str] | None = None,
    ) -> None:
        """Execute a batch of ready nodes in parallel."""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(ready))
        try:
            future_map: dict[concurrent.futures.Future, ExecutionNode] = {}
            for node in ready:
                future = executor.submit(
                    self._execute_node,
                    node,
                    target=target,
                    extracted_params=extracted_params,
                    timeframe=timeframe,
                    bound_params_out=bound_params_out,
                    budget=budget,
                    budget_lock=budget_lock,
                    allowed_sources=allowed_sources,
                )
                future_map[future] = node
                metrics.tool_calls += 1

            parallel_timeout = max(timeout_deadline - _time.perf_counter(), 0.0)
            try:
                for future in concurrent.futures.as_completed(
                    future_map, timeout=parallel_timeout
                ):
                    node = future_map[future]
                    cap_name = node.execution_step.capability.name
                    try:
                        result = future.result()
                    except (
                        RuntimeError,
                        ValueError,
                        TypeError,
                        OSError,
                        concurrent.futures.CancelledError,
                    ) as exc:
                        message = f"Execution runtime error: {exc}"
                        result = ToolResult(
                            success=False,
                            error=message,
                            capability_status=CapabilityStatus.COLLECTION_FAILED,
                            capability_error=internal_error(message),
                        )
                    results[cap_name] = result
                    metrics.tool_calls += len(result.recovery_attempts)
                    metrics.recovery_attempts += len(result.recovery_attempts)
                    metrics.recovery_successes += int(result.recovered_by is not None)
                    self._record_security_metrics(metrics, result)
                    if result.success:
                        record_success(cap_name)
            except concurrent.futures.TimeoutError:
                for fut, nd in future_map.items():
                    if not fut.done():
                        fut.cancel()
                        cname = nd.execution_step.capability.name
                        if cname not in results:
                            results[cname] = ToolResult(
                                success=False,
                                error=f"Execution timed out after {overall_timeout}s",
                                capability_status=CapabilityStatus.COLLECTION_FAILED,
                            )
                metrics.timed_out = True
        finally:
            # Context-manager shutdown waits for running calls and would violate
            # the investigation's hard wall-clock budget after a timeout.
            executor.shutdown(wait=False, cancel_futures=True)

    def _execute_node(
        self,
        node: ExecutionNode,
        target: str = "localhost",
        extracted_params: object = None,
        timeframe: object = None,
        bound_params_out: dict[str, dict[str, object]] | None = None,
        allow_recovery: bool = True,
        budget: ExecutionBudget | None = None,
        budget_lock: threading.Lock | None = None,
        allowed_sources: frozenset[str] | None = None,
    ) -> ToolResult:
        """Execute a single node by dispatching through KnowledgeTool."""
        cap_name = node.execution_step.capability.name
        metadata_override = node.execution_step.metadata
        route_name = str(metadata_override.get("base_capability") or cap_name)
        forced_source = metadata_override.get("forced_source")
        source_filter = (
            frozenset({str(forced_source)})
            if isinstance(forced_source, str)
            else allowed_sources
        )

        routed = self._router.resolve_with_metadata(
            route_name,
            self._routing_params(extracted_params, timeframe),
            allowed_sources=source_filter,
        )
        if routed is None:
            return ToolResult(
                success=False,
                error=f"No route configured for capability: {cap_name}",
                capability_status=CapabilityStatus.UNSUPPORTED,
            )

        (source, resource), metadata = routed

        if source == "localhost" and target != "localhost":
            source = target

        try:
            bound = self._parameter_binder.bind(
                source=source,
                resource=resource,
                metadata=metadata,
                extracted_params=extracted_params,
                timeframe=timeframe,
            )
        except ParameterBindingError as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                capability_status=CapabilityStatus.INVALID_PARAMETERS,
                source=source,
                source_kind=self._knowledge_tool.source_kind(source),
                resource=resource,
                produced_fact_names=self._produced_fact_names(metadata),
                schema_version="1",
            )
        arguments = bound.arguments
        if bound_params_out is not None:
            bound_params_out[cap_name] = {
                key: value
                for key, value in arguments.items()
                if key not in {"source", "resource"}
            }

        try:
            result = self._retry.execute(
                lambda: self._knowledge_tool.execute(arguments),
                context=cap_name,
                should_retry_result=is_recoverable_result,
            )
            result = replace(
                result,
                source=source,
                source_kind=self._knowledge_tool.source_kind(source),
                resource=resource,
                parameters=tuple(
                    sorted(
                        (str(key), value)
                        for key, value in arguments.items()
                        if key not in {"source", "resource"}
                    )
                ),
                schema_version="1",
            )
            if allow_recovery and not result.success:
                result = self._recover_node(
                    cap_name,
                    result,
                    metadata,
                    target=target,
                    extracted_params=extracted_params,
                    timeframe=timeframe,
                    bound_params_out=bound_params_out,
                    budget=budget,
                    budget_lock=budget_lock,
                    allowed_sources=allowed_sources,
                )
            return result
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            message = f"KnowledgeTool dispatch failed for {cap_name}: {exc}"
            return ToolResult(
                success=False,
                error=message,
                capability_status=CapabilityStatus.COLLECTION_FAILED,
                capability_error=internal_error(message),
                source=source,
                source_kind=self._knowledge_tool.source_kind(source),
                resource=resource,
                parameters=tuple(
                    sorted(
                        (str(key), value)
                        for key, value in arguments.items()
                        if key not in {"source", "resource"}
                    )
                ),
                produced_fact_names=self._produced_fact_names(metadata),
                schema_version="1",
            )

    def _recover_node(
        self,
        capability_name: str,
        result: ToolResult,
        metadata: dict[str, object],
        *,
        target: str,
        extracted_params: object,
        timeframe: object,
        bound_params_out: dict[str, dict[str, object]] | None,
        budget: ExecutionBudget | None = None,
        budget_lock: threading.Lock | None = None,
        allowed_sources: frozenset[str] | None = None,
    ) -> ToolResult:
        alternatives = self._metadata_strings(metadata, "alternatives")
        recoverable_errors = self._metadata_strings(
            metadata, "recoverable_errors"
        )
        specs: dict[str, CapabilityRecoverySpec] = {
            capability_name: CapabilityRecoverySpec(
                capability_name, alternatives, recoverable_errors
            )
        }
        # Load at most one further declaration so the generic engine can use
        # its depth-two contract without recursively expanding the runtime.
        for name in alternatives:
            routed = self._router.resolve_with_metadata(
                name,
                self._routing_params(extracted_params, timeframe),
                allowed_sources=allowed_sources,
            )
            if routed is None:
                continue
            _, alternative_metadata = routed
            specs[name] = CapabilityRecoverySpec(
                name=name,
                alternatives=self._metadata_strings(
                    alternative_metadata, "alternatives"
                ),
                recoverable_errors=self._metadata_strings(
                    alternative_metadata, "recoverable_errors"
                ),
            )

        recovery = CapabilityRecovery(specs, max_depth=2)

        def execute_alternative(name: str) -> ToolResult:
            node = ExecutionNode(
                execution_step=ExecutionStep(
                    capability=CapabilityReference(
                        name=name,
                        evidence_name=name,
                    )
                )
            )
            return self._execute_node(
                node,
                target=target,
                extracted_params=extracted_params,
                timeframe=timeframe,
                bound_params_out=bound_params_out,
                allow_recovery=False,
                budget=budget,
                budget_lock=budget_lock,
                allowed_sources=allowed_sources,
            )

        def can_attempt() -> bool:
            # DR: reserve budget for a recovery attempt *before* it is
            # dispatched (not after, via a post-hoc metrics addition) so a
            # caller's configured hard limits (max_capabilities,
            # max_estimated_cost, max_total_duration) can never be
            # exceeded even mid-round. When no budget was supplied,
            # recovery is unbounded (legacy behaviour for callers that
            # don't pass one, e.g. direct ExecutionRuntime.execute() use
            # without a shared budget).
            if budget is None:
                return True
            if budget_lock is None:
                return budget.try_reserve_capability()
            with budget_lock:
                return budget.try_reserve_capability()

        outcome = recovery.recover(
            capability_name,
            result,
            execute_alternative,
            available_capabilities=set(self._router.available_routes()),
            can_attempt=can_attempt,
        )
        if not outcome.attempts:
            return result
        return replace(
            outcome.result,
            recovery_attempts=tuple(
                attempt.to_dict() for attempt in outcome.attempts
            ),
            recovered_by=outcome.recovered_by,
        )

    @staticmethod
    def _metadata_strings(
        metadata: dict[str, object], key: str
    ) -> tuple[str, ...]:
        raw = metadata.get(key, ())
        if not isinstance(raw, (list, tuple)):
            return ()
        return tuple(item for item in raw if isinstance(item, str))

    def validate_graph_parameters(
        self,
        graph: ExecutionGraph,
        *,
        target: str,
        extracted_params: object = None,
        timeframe: object = None,
        allowed_sources: frozenset[str] | None = None,
    ) -> None:
        """Fail before dispatch if any planned capability has invalid arguments."""
        routing_params = self._routing_params(extracted_params, timeframe)
        for node in graph.nodes:
            cap_name = node.execution_step.capability.name
            metadata_override = node.execution_step.metadata
            route_name = str(metadata_override.get("base_capability") or cap_name)
            forced_source = metadata_override.get("forced_source")
            source_filter = (
                frozenset({str(forced_source)})
                if isinstance(forced_source, str)
                else allowed_sources
            )
            routed = self._router.resolve_with_metadata(
                route_name,
                routing_params,
                allowed_sources=source_filter,
            )
            if routed is None:
                continue
            (source, resource), metadata = routed
            if source == "localhost" and target != "localhost":
                source = target
            self._parameter_binder.bind(
                source=source,
                resource=resource,
                metadata=metadata,
                extracted_params=extracted_params,
                timeframe=timeframe,
            )

    def cache_parameters(
        self,
        node: ExecutionNode,
        *,
        target: str,
        extracted_params: object = None,
        timeframe: object = None,
        allowed_sources: frozenset[str] | None = None,
    ) -> tuple[tuple[str, object], ...]:
        """Return the same normalized bound parameters used for dispatch."""

        cap_name = node.execution_step.capability.name
        metadata_override = node.execution_step.metadata
        route_name = str(metadata_override.get("base_capability") or cap_name)
        forced_source = metadata_override.get("forced_source")
        source_filter = (
            frozenset({str(forced_source)})
            if isinstance(forced_source, str)
            else allowed_sources
        )
        routed = self._router.resolve_with_metadata(
            route_name,
            self._routing_params(extracted_params, timeframe),
            allowed_sources=source_filter,
        )
        if routed is None:
            return ()
        (source, resource), metadata = routed
        if source == "localhost" and target != "localhost":
            source = target
        bound = self._parameter_binder.bind(
            source=source,
            resource=resource,
            metadata=metadata,
            extracted_params=extracted_params,
            timeframe=timeframe,
        )
        return tuple(
            sorted(
                (str(key), value)
                for key, value in bound.arguments.items()
                if key not in {"source", "resource"}
            )
        )

    @staticmethod
    def _produced_fact_names(metadata: dict[str, object]) -> tuple[str, ...]:
        raw = metadata.get("produces_facts", ())
        if not isinstance(raw, (list, tuple)):
            return ()
        return tuple(name for name in raw if isinstance(name, str))

    @staticmethod
    def _routing_params(
        extracted_params: object, timeframe: object
    ) -> dict[str, object]:
        params = ParameterBinder._as_dict(extracted_params)
        params["__timeframe__"] = timeframe
        return params

    @staticmethod
    def _record_security_metrics(metrics: RuntimeMetrics, result: ToolResult) -> None:
        if not result.security_inspected:
            return
        metrics.security_inspections_total += 1
        if result.security_allowed:
            metrics.security_inspections_passed += 1
        else:
            metrics.security_inspections_blocked += 1
