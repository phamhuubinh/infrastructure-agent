from __future__ import annotations

import json
from typing import Any


def generate_human_report(reports: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("BENCHMARK REPORT")
    lines.append("=" * 60)
    lines.append("")

    domains: dict[str, list[dict[str, Any]]] = {}
    for r in reports:
        domains.setdefault(r["domain"], []).append(r)

    grand_total = 0.0
    grand_count = 0
    total_elapsed = 0.0

    for domain in sorted(domains):
        domain_reports = domains[domain]
        lines.append("-" * 40)
        lines.append(f"Domain: {domain.upper()} ({len(domain_reports)} scenarios)")
        lines.append("-" * 40)

        domain_total = 0.0
        for r in domain_reports:
            s = r["scores"]
            total = s["total"]
            domain_total += total

            am = r.get("assessment_metrics", {})
            cov_str = ""
            if am:
                cov_str = (
                    f" ev_cov={am.get('evidence_coverage', 0):.2f}"
                    f" grd={am.get('grounding', 0):.2f}"
                    f" comp={am.get('completeness', 0):.2f}"
                )

            status = "OK" if total >= 0.7 else "FAIL" if total < 0.4 else "WARN"
            lines.append(
                f"  {r['benchmark']:<30} {status} "
                f"total={total:.2f} "
                f"reason={s['reasoning']:.2f} "
                f"eff={s['efficiency']:.2f} "
                f"evid={s['evidence']:.2f} "
                f"saf={s['safety']:.2f} "
                f"iter={r['iterations']} "
                f"{r['elapsed']:.1f}s"
                f"{cov_str}"
            )

        domain_avg = domain_total / len(domain_reports)
        lines.append(f"  Domain average: {domain_avg:.2f}")
        lines.append("")
        grand_total += domain_total
        grand_count += len(domain_reports)
        for r in domain_reports:
            total_elapsed += r["elapsed"]

    overall = grand_total / grand_count if grand_count else 0
    lines.append("=" * 60)
    lines.append(f"OVERALL SCORE: {overall:.2f}")
    lines.append(f"Total scenarios: {grand_count}")
    lines.append(f"Total elapsed: {total_elapsed:.1f}s")
    lines.append("=" * 60)

    return "\n".join(lines)


def generate_json_report(reports: list[dict[str, Any]]) -> str:
    domains: dict[str, list[dict[str, Any]]] = {}
    for r in reports:
        domains.setdefault(r["domain"], []).append(r)

    domain_scores: dict[str, float] = {}
    for domain, domain_reports in domains.items():
        scores = [r["scores"]["total"] for r in domain_reports]
        domain_scores[domain] = round(sum(scores) / len(scores), 2)

    all_scores = [r["scores"]["total"] for r in reports]
    overall = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0

    # Aggregate assessment metrics across all scenarios.
    all_assessment: list[dict[str, float]] = [
        r.get("assessment_metrics", {})
        for r in reports
        if r.get("assessment_metrics")
    ]
    avg_assessment: dict[str, float] = {}
    if all_assessment:
        metric_keys = all_assessment[0].keys()
        for key in metric_keys:
            values = [m[key] for m in all_assessment if key in m]
            avg_assessment[key] = round(sum(values) / len(values), 4) if values else 0.0

    summary = {
        "overall": overall,
        "domain_scores": domain_scores,
        "scenarios": len(reports),
        "total_elapsed": round(sum(r["elapsed"] for r in reports), 1),
        "assessment": avg_assessment,
        "results": [
            {
                "benchmark": r["benchmark"],
                "domain": r["domain"],
                "total": r["scores"]["total"],
                "reasoning": r["scores"]["reasoning"],
                "efficiency": r["scores"]["efficiency"],
                "evidence": r["scores"]["evidence"],
                "safety": r["scores"]["safety"],
                "iterations": r["iterations"],
                "elapsed": r["elapsed"],
                "assessment_metrics": r.get("assessment_metrics", {}),
                "errors": r["errors"],
            }
            for r in reports
        ],
    }

    return json.dumps(summary, indent=2)
