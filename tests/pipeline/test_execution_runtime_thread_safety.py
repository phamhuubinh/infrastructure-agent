from __future__ import annotations

import threading
from unittest import mock

from src.pipeline.capability_reference import CapabilityReference
from src.pipeline.capability_router import CapabilityRouter
from src.pipeline.execution_graph import ExecutionGraph, ExecutionNode
from src.pipeline.execution_plan import ExecutionStep
from src.pipeline.execution_runtime import ExecutionRuntime
from src.shared.execution.tool_result import ToolResult
from src.tool.knowledge_tool import KnowledgeTool


def _step(cap_name: str, evidence_name: str = "") -> ExecutionStep:
    return ExecutionStep(
        capability=CapabilityReference(
            name=cap_name, evidence_name=evidence_name or cap_name
        ),
    )


def _node(step: ExecutionStep, deps: tuple[str, ...] = ()) -> ExecutionNode:
    return ExecutionNode(execution_step=step, depends_on=deps)


def _make_thread_safe_mock() -> mock.Mock:
    """Return a KnowledgeTool mock that is safe for concurrent access."""
    mt = mock.Mock(spec=KnowledgeTool)
    mt.execute.return_value = ToolResult(success=True, data={})
    return mt


# ---------------------------------------------------------------------------
# ExecutionRuntime thread safety
# ---------------------------------------------------------------------------


class TestExecutionRuntimeThreadSafety:
    """Thread-safety tests for ExecutionRuntime.

    ExecutionRuntime uses a shared results dict and completed set
    protected by threading.Lock. These tests verify that concurrent
    access patterns (multiple execute() calls, shared state) behave
    correctly under load.
    """

    def test_concurrent_execute_same_instance(self) -> None:
        """Multiple threads calling execute() concurrently on the same
        ExecutionRuntime instance must not corrupt internal state."""
        mock_kt = _make_thread_safe_mock()

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        steps = [
            _step("System Information"),
            _step("CPU Information", "CPU"),
            _step("Memory Information", "Memory"),
        ]
        graph = _graph_from_steps(steps)

        n_threads = 8
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute(tid: int) -> None:
            barrier.wait()
            try:
                runtime.execute(graph)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_execute, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent execute: {errors}"

    def test_concurrent_execute_different_graphs(self) -> None:
        """Multiple threads calling execute() with different graphs must
        each produce correct results."""
        mock_kt = _make_thread_safe_mock()

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        n_threads = 8

        graph_a = _graph_from_steps(
            [
                _step("System Information"),
                _step("CPU Information", "CPU"),
            ]
        )
        graph_b = _graph_from_steps(
            [
                _step("Memory Information", "Memory"),
                _step("Swap Information", "Swap"),
            ]
        )

        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute(graph_id: int) -> None:
            barrier.wait()
            graph = graph_a if graph_id % 2 == 0 else graph_b
            try:
                results, _ = runtime.execute(graph)
                if graph_id % 2 == 0:
                    assert "System Information" in results
                    assert "CPU Information" in results
                else:
                    assert "Memory Information" in results
                    assert "Swap Information" in results
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_execute, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent execute with different graphs: {errors}"
        )

    def test_concurrent_execute_with_shared_router(self) -> None:
        """Multiple threads sharing a CapabilityRouter instance must not
        cause route corruption."""
        mock_kt = _make_thread_safe_mock()

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)

        n_threads = 6
        runtimes = [
            ExecutionRuntime(knowledge_tool=mock_kt, router=router)
            for _ in range(n_threads)
        ]

        graph = _graph_from_steps(
            [
                _step("System Information"),
                _step("CPU Information", "CPU"),
            ]
        )

        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute(rt: ExecutionRuntime) -> None:
            barrier.wait()
            try:
                results, _ = rt.execute(graph)
                assert "System Information" in results
                assert "CPU Information" in results
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_execute, args=(rt,)) for rt in runtimes]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent execute with shared router: {errors}"
        )

    def test_concurrent_execute_high_contention(self) -> None:
        """High-contention scenario: many threads execute the same graph
        on the same runtime instance concurrently."""
        mock_kt = _make_thread_safe_mock()

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        n_threads = 16
        iterations = 5

        graph = _graph_from_steps(
            [
                _step("System Information"),
                _step("CPU Information", "CPU"),
                _step("Memory Information", "Memory"),
                _step("Swap Information", "Swap"),
            ]
        )

        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute() -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    results, _ = runtime.execute(graph)
                    assert len(results) == 4
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=_execute) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during high-contention concurrent execute: {errors}"

    def test_concurrent_execute_with_early_completion(self) -> None:
        """Multiple threads executing with early completion must all
        produce correct skip behavior."""
        mock_kt = _make_thread_safe_mock()

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        steps = [
            _step("CPU Information", "CPU"),
            _step("Memory Information", "Memory"),
            _step("Swap Information", "Swap"),
        ]
        graph = _graph_from_steps(
            steps,
            deps={"Swap Information": ("CPU Information", "Memory Information")},
        )

        n_threads = 8
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute() -> None:
            barrier.wait()
            try:
                results, metrics = runtime.execute(
                    graph,
                    required_evidence_names={"CPU"},
                )
                assert "CPU Information" in results
                assert "Memory Information" in results
                assert "Swap Information" in results
                assert results["Swap Information"].success is False
                assert "Skipped" in (results["Swap Information"].error or "")
                assert metrics.early_completed is True
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_execute) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent execute with early completion: {errors}"
        )

    def test_concurrent_execute_timeout_handling(self) -> None:
        """Timeout handling under concurrent execution must not leave
        stale state or raise unexpected exceptions."""
        mock_kt = mock.Mock(spec=KnowledgeTool)
        import time as _time

        def _slow(_args):
            _time.sleep(5)
            return ToolResult(success=True, data={})

        mock_kt.execute.side_effect = _slow

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        graph = _graph_from_steps(
            [
                _step("System Information"),
                _step("CPU Information", "CPU"),
            ]
        )

        n_threads = 6
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _execute() -> None:
            barrier.wait()
            try:
                results, metrics = runtime.execute(graph, overall_timeout=0.3)
                assert len(results) <= 2
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_execute) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent execute with timeout: {errors}"

    def test_deterministic_output_under_concurrent_load(self) -> None:
        """Running the same graph N times concurrently should produce
        deterministic results (same number of successful nodes)."""
        mock_kt = _make_thread_safe_mock()

        real_kt = KnowledgeTool()
        router = CapabilityRouter()
        router.build_routes(real_kt)
        runtime = ExecutionRuntime(knowledge_tool=mock_kt, router=router)

        graph = _graph_from_steps(
            [
                _step("System Information"),
                _step("CPU Information", "CPU"),
                _step("Memory Information", "Memory"),
            ]
        )

        n_threads = 6
        runs = 3
        success_counts: list[int] = []

        for run_idx in range(runs):
            barrier = threading.Barrier(n_threads)
            errors: list[Exception] = []
            results_lock = threading.Lock()
            run_results: list[int] = []

            def _execute(
                _barrier: threading.Barrier = barrier,
                _results_lock: threading.Lock = results_lock,
                _run_results: list[int] = run_results,
                _errors: list[Exception] = errors,
            ) -> None:
                _barrier.wait()
                try:
                    _, metrics = runtime.execute(graph)
                    with _results_lock:
                        _run_results.append(metrics.successful_nodes)
                except Exception as e:
                    _errors.append(e)

            threads = [threading.Thread(target=_execute) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, (
                f"Errors during deterministic test run {run_idx}: {errors}"
            )
            success_counts.append(sum(run_results))

        assert all(c == success_counts[0] for c in success_counts), (
            f"Non-deterministic: success counts differ across runs: {success_counts}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph_from_steps(
    steps: list[ExecutionStep],
    deps: dict[str, tuple[str, ...]] | None = None,
) -> ExecutionGraph:
    if deps is None:
        deps = {}
    nodes: list[ExecutionNode] = []
    for step in steps:
        nodes.append(
            ExecutionNode(
                execution_step=step,
                depends_on=deps.get(step.capability.name, ()),
            ),
        )
    return ExecutionGraph(nodes=tuple(nodes))
