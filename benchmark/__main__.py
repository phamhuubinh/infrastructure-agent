from __future__ import annotations

import argparse
from typing import Any

from benchmark.dataset import BENCHMARKS
from benchmark.report import generate_human_report, generate_json_report
from benchmark.scoring import score


def _run_benchmarks(
    domain: str | None,
    export_json: bool,
) -> list[dict[str, Any]]:
    from src.agent.runtime_factory import create_deterministic_agent

    agent = create_deterministic_agent()

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
            results.append({
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
            })
            total = scores_dict["total"]
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
                "exception": str(exc),
            })

    return results


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
        "--model", type=str, default=None,
        help="Model name for comparison (not yet implemented)"
    )
    args = parser.parse_args()

    print("\nBenchmark Suite (deterministic runtime)")
    print("=" * 60)

    results = _run_benchmarks(args.domain, args.json)

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
