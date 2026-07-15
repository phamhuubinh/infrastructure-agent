from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any

from src.model.protocol.prompt_builder_v2 import PROMPT_VERSIONS

from benchmark.assessment_evaluator import AssessmentExpected
from benchmark.assessment_evaluator import evaluate as evaluate_assessment
from benchmark.assessment_evaluator import metrics_to_dict
from benchmark.dataset import BENCHMARKS
from benchmark.metadata import collect_benchmark_metadata
from benchmark.registry import detect_regressions
from benchmark.registry import save_results
from benchmark.report import generate_human_report, generate_json_report
from benchmark.scoring import score


def _timestamped_log_path() -> Path:
    """Return a log path with a timestamp to prevent overwriting."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    return Path(f"benchmark_results_{ts}.log")


def _export_csv(results: list[dict[str, Any]], path: Path) -> None:
    """Export benchmark results to CSV format."""
    fieldnames = [
        "benchmark", "domain", "total", "reasoning", "efficiency",
        "evidence", "safety", "elapsed", "iterations",
        "evidence_coverage", "grounding", "completeness", "overall",
        "errors",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            am = r.get("assessment_metrics", {})
            row = {
                "benchmark": r["benchmark"],
                "domain": r["domain"],
                "total": r["scores"]["total"],
                "reasoning": r["scores"]["reasoning"],
                "efficiency": r["scores"]["efficiency"],
                "evidence": r["scores"]["evidence"],
                "safety": r["scores"]["safety"],
                "elapsed": r["elapsed"],
                "iterations": r["iterations"],
                "evidence_coverage": am.get("evidence_coverage", ""),
                "grounding": am.get("grounding", ""),
                "completeness": am.get("completeness", ""),
                "overall": am.get("overall", ""),
                "errors": "; ".join(r.get("errors", [])),
            }
            writer.writerow(row)


def _export_markdown(results: list[dict[str, Any]], path: Path) -> None:
    """Export benchmark summary as Markdown table."""
    domains: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        domains.setdefault(r["domain"], []).append(r)

    lines = [
        "# Benchmark Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    all_totals = []
    for domain in sorted(domains):
        dr = domains[domain]
        lines.append(f"## {domain.upper()}")
        lines.append("")
        lines.append("| Benchmark | Total | Reasoning | Efficiency | Evidence | Safety | Elapsed |")
        lines.append("|-----------|-------|-----------|------------|----------|--------|---------|")
        for r in dr:
            s = r["scores"]
            lines.append(
                f"| {r['benchmark']} | {s['total']:.2f} | {s['reasoning']:.2f} "
                f"| {s['efficiency']:.2f} | {s['evidence']:.2f} | {s['safety']:.2f} "
                f"| {r['elapsed']:.1f}s |"
            )
            all_totals.append(s["total"])
        lines.append("")

    if all_totals:
        scores = sorted(all_totals)
        n = len(scores)
        mean = sum(scores) / n
        mid = n // 2
        median = scores[mid] if n % 2 else (scores[mid - 1] + scores[mid]) / 2
        variance = sum((x - mean) ** 2 for x in scores) / n
        lines.append("## Summary Statistics")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Count | {n} |")
        lines.append(f"| Mean | {mean:.4f} |")
        lines.append(f"| Median | {median:.4f} |")
        lines.append(f"| Std Dev | {variance ** 0.5:.4f} |")
        lines.append(f"| Min | {min(scores):.4f} |")
        lines.append(f"| Max | {max(scores):.4f} |")
        lines.append("")

    path.write_text("\n".join(lines))


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


def _aggregate_repeated(
    all_runs: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Aggregate N repeated benchmark runs.

    Takes the first run's results as the canonical output,
    adding _variance fields to each result's assessment_metrics.
    """
    if len(all_runs) <= 1:
        return all_runs[0] if all_runs else []

    canonical = all_runs[0]
    metric_keys = ["evidence_coverage", "grounding", "completeness", "overall"]

    for i, base in enumerate(canonical):
        bm_name = base["benchmark"]
        values: dict[str, list[float]] = {k: [] for k in metric_keys}
        for run in all_runs:
            for r in run:
                if r["benchmark"] == bm_name:
                    am = r.get("assessment_metrics", {})
                    for k in metric_keys:
                        values[k].append(am.get(k, 0.0))
                    break

        am = base.get("assessment_metrics", {})
        for k in metric_keys:
            if values[k]:
                vals = values[k]
                mean = sum(vals) / len(vals)
                variance = sum((x - mean) ** 2 for x in vals) / len(vals)
                am[f"{k}_min"] = round(min(vals), 4)
                am[f"{k}_max"] = round(max(vals), 4)
                am[f"{k}_mean"] = round(mean, 4)
                am[f"{k}_std"] = round(variance ** 0.5, 4)

    return canonical


def _build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="Run benchmarks N times and aggregate variance"
    )
    parser.add_argument(
        "--prompt", type=str, default="compact",
        choices=list(PROMPT_VERSIONS.keys()),
        help="Prompt version to use for assessment"
    )
    parser.add_argument(
        "--csv", action="store_true", default=True,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-csv", action="store_false", dest="csv",
        help="Skip CSV export"
    )
    parser.add_argument(
        "--markdown", action="store_true", default=True,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-markdown", action="store_false", dest="markdown",
        help="Skip Markdown export"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Set prompt version before any assessment calls.
    from src.model.protocol.prompt_builder_v2 import set_prompt_version
    set_prompt_version(args.prompt)

    metadata = collect_benchmark_metadata(
        server_name=args.server,
        model=args.model,
    )
    runtime_label = args.server or metadata.get("provider", "mock") or "mock"
    print(f"\nBenchmark Suite (runtime: {runtime_label}, repeat={args.repeat})")
    print("=" * 60)

    # Run N times for reproducibility measurement.
    all_runs: list[list[dict[str, Any]]] = []
    for rep in range(args.repeat):
        if args.repeat > 1:
            print(f"\n--- Run {rep + 1}/{args.repeat} ---")
        results = _run_benchmarks(
            domain=args.domain,
            export_json=args.json,
            server_name=args.server,
            model=args.model,
        )
        all_runs.append(results)

    results = _aggregate_repeated(all_runs)

    # Persist if requested.
    if args.save:
        history = save_results(results, metadata=metadata)
        run_ids = sorted(history, key=lambda x: int(x) if x.isdigit() else 0)
        current_id = run_ids[-1]
        print(f"\nResults saved to benchmark history (run #{current_id}).")

    # Check for regressions against matching previous run.
    if args.save:
        regressions = detect_regressions(results, new_metadata=metadata)
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
        report_json = generate_json_report(results, metadata=metadata)
        print(report_json)
        # Write to timestamped JSON file.
        log_path = _timestamped_log_path().with_suffix(".json")
        log_path.write_text(report_json)
        print(f"\nReport saved to {log_path}")
    else:
        report_str = generate_human_report(results, metadata=metadata)
        print(report_str)
        # Write to timestamped log file.
        log_path = _timestamped_log_path()
        log_path.write_text(report_str)
        print(f"\nLog saved to {log_path}")

    # Always export CSV and Markdown summary.
    if args.csv:
        csv_path = log_path.with_suffix(".csv")
        _export_csv(results, csv_path)
        print(f"CSV exported to {csv_path}")

    if args.markdown:
        md_path = log_path.with_suffix(".md")
        _export_markdown(results, md_path)
        print(f"Markdown exported to {md_path}")

    if args.domain:
        all_in_domain = [b for b in BENCHMARKS if b.domain == args.domain]
        print(f"\nDomain '{args.domain}': {len(results)}/{len(all_in_domain)} executed")

    print("\nDone.")


if __name__ == "__main__":
    main()
