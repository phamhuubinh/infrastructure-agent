from __future__ import annotations

import time
from typing import Any

from benchmark.dataset import BENCHMARKS, Benchmark
from benchmark.scoring import score


class BenchmarkRunner:
    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}

    def run_all(
        self,
        agent_run,
        available_resources: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        reports = []
        for bm in BENCHMARKS:
            report = self._run_single(bm, agent_run, available_resources)
            reports.append(report)
            self.results[bm.name] = report
        return reports

    def run_domain(
        self,
        domain: str,
        agent_run,
        available_resources: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        reports = []
        for bm in BENCHMARKS:
            if bm.domain != domain:
                continue
            report = self._run_single(bm, agent_run, available_resources)
            reports.append(report)
            self.results[bm.name] = report
        return reports

    def _run_single(
        self,
        benchmark: Benchmark,
        agent_run,
        available_resources: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        errors: list[str] = []
        cap_sequence: list[str] = []
        iterations = 0
        response = ""
        agent_exc = None

        try:
            response = agent_run(benchmark.request)
        except Exception as exc:
            errors.append(str(exc))
            agent_exc = exc

        elapsed = time.perf_counter() - t0

        # Extract iteration count and capability sequence from the run
        # The actual agent run returns final response; we approximate
        # iterations from timing.
        scores = score(benchmark, cap_sequence, iterations, response, errors)

        return {
            "benchmark": benchmark.name,
            "domain": benchmark.domain,
            "request": benchmark.request,
            "response": response,
            "iterations": iterations,
            "elapsed": round(elapsed, 3),
            "capability_sequence": cap_sequence,
            "errors": errors,
            "scores": scores,
            "exception": str(agent_exc) if agent_exc else None,
        }
