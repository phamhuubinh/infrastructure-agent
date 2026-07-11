from __future__ import annotations

import argparse
from typing import Any

from benchmark.assessment_evaluator import AssessmentExpected
from benchmark.assessment_evaluator import evaluate as evaluate_assessment
from benchmark.assessment_evaluator import metrics_to_dict
from benchmark.dataset import BENCHMARKS
from benchmark.metadata import collect_benchmark_metadata
from benchmark.registry import detect_regressions
from benchmark.registry import save_results
from benchmark.report import generate_human_report, generate_json_report
from benchmark.scoring import score


def _run_benchmarks(
    domain: str | None,
    export_json: bool,
    server_name: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    from src.agent.runtime_factory import create_deterministic_agent

    agent = create_deterministic_agent(
        server_name=server_name,
        model=model,
    )

    benchmarks = [b for b in BENCHMARKS if domain is None or b.domain == domain]

    results: list[dict[str, Any]] = []

    for bm in benchmarks:
        print(f"  [{bm.domain}] {bm.name}... ", end="", flush=True)
        try:
            import time

            t0 = time.perf_counter()
            response = agent.run(bm.request)
            elapsed = time.perf_counter() - t0
            errors: list[str] = []

            scores_dict = score(bm, [], 1, response, errors)

            result: dict[str, Any] = {
                "benchmark": bm.name,
                "domain": bm.domain,
                "request": bm.request,
                "response": response,
                "iterations": 1,
                "elapsed": round(elapsed, 3),
                "capability_sequence": [],
                "errors": errors,
                "scores": scores_dict,
                "exception": None,
            }

            if bm.expected_evidence:
                expected = AssessmentExpected(
                    evidence=tuple(bm.expected_evidence),
                    recommendations=tuple(bm.expected_recommendations),
                    sections=tuple(bm.expected_sections),
                )
                prompt = _get_prompt(bm.request)
                metrics = evaluate_assessment(
                    response=response,
                    expected=expected,
                    prompt_size=len(prompt) if prompt else 0,
                    completion_size=len(response),
                )
                result["assessment_metrics"] = metrics_to_dict(metrics)
            else:
                result["assessment_metrics"] = {}

            results.append(result)

            total = scores_dict.get("total", 0)
            status = "PASS" if total >= 0.7 else "FAIL" if total < 0.4 else "WARN"
            print(f"{status} ({total:.2f})")
        except Exception as exc:
            print(f"ERROR: {exc}")
            results.append({
                "benchmark": bm.name,
                "domain": bm.domain,
                "request": bm.request,
                "response": "",
                "iterations": 0,
                "elapsed": 0,
                "capability_sequence": [],
                "errors": [str(exc)],
                "scores": {"total": 0, "reasoning": 0, "efficiency": 0, "evidence": 0, "safety": 0},
                "assessment_metrics": {},
                "exception": str(exc),
            })

    return results


def _get_prompt(request: str) -> str:
    from src.pipeline.assessment_adapter import AssessmentAdapter
    from src.pipeline.assessment_request import AssessmentRequest
    from src.model.protocol.prompt_builder_v2 import build_assessment_prompt

    req = AssessmentRequest(raw_request=request)
    return build_assessment_prompt(req)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Agent Benchmark Suite")
    parser.add_argument(
        "--domain", type=str, default=None,
        help="Run only benchmarks for a specific domain"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Export report as JSON"
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Persist benchmark results to history"
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override model name"
    )
    parser.add_argument(
        "--server", type=str, default=None,
        help="Model server name from servers.json"
    )
    args = parser.parse_args()

    runtime_label = args.server or "mock"
    print(f"\nBenchmark Suite (runtime: {runtime_label})")
    print("=" * 60)

    results = _run_benchmarks(
        domain=args.domain,
        export_json=args.json,
        server_name=args.server,
        model=args.model,
    )

    # Persist if requested.
    if args.save:
        metadata = collect_benchmark_metadata(
            server_name=args.server,
            model=args.model,
        )
        history = save_results(results, metadata=metadata)
        run_id = max(history.keys())
        print(f"\nResults saved to benchmark history (run #{run_id}).")

    # Check for regressions against previous run.
    if args.save:
        regressions = detect_regressions(results)
        if regressions:
            print("\nREGRESSIONS DETECTED:")
            for reg in regressions:
                print(
                    f"  {reg['benchmark']}: {reg['metric']} "
                    f"{reg['previous']:.2f} → {reg['new']:.2f} "
                    f"({reg['delta']:+.2f})"
                )
        else:
            print("\nNo regressions detected.")

    print()
    if args.json:
        print(generate_json_report(results))
    else:
        print(generate_human_report(results))

    if args.domain:
        all_in_domain = [b for b in BENCHMARKS if b.domain == args.domain]
        print(f"\nDomain '{args.domain}': {len(results)}/{len(all_in_domain)} executed")

    print("\nDone.")


if __name__ == "__main__":
    main()
