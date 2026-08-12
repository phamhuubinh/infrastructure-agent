"""Offline acceptance gates for deterministic QA reports (DR1-807..811).

This module consumes the JSON shape emitted by :mod:`scripts.qa.run_baseline`.
It intentionally never creates an agent, contacts a model, or executes a
tool; CI can therefore enforce the same gates without live infrastructure.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class GateViolation:
    gate: str
    message: str
    case_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    metrics: dict[str, Any]
    violations: tuple[GateViolation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "metrics": self.metrics,
            "violations": [asdict(violation) for violation in self.violations],
        }


def percentile(values: Iterable[float], fraction: float) -> float | None:
    """Return the nearest-rank percentile for a bounded fixture sample."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = min(max(int(len(ordered) * fraction), 0), len(ordered) - 1)
    return round(ordered[index], 3)


def _median(values: Iterable[float]) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[midpoint], 3)
    return round((ordered[midpoint - 1] + ordered[midpoint]) / 2, 3)


def _numbers(cases: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for case in cases:
        metrics = case.get("actual", {}).get("runtime_metrics") or {}
        response_metrics = case.get("actual", {}).get("response_metrics") or {}
        value = metrics.get(key, response_metrics.get(key))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def runtime_summary(report: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    """Aggregate execution metrics needed for performance/tool-budget gates."""
    cases = report.get("cases", [])
    if not isinstance(cases, list):
        cases = []
    elapsed = [
        float(case["elapsed_ms"])
        for case in cases
        if isinstance(case.get("elapsed_ms"), (int, float))
    ]
    return {
        "latency_ms": {"median": _median(elapsed), "p95": percentile(elapsed, 0.95)},
        "tool_calls": {
            "median": _median(_numbers(cases, "tool_calls")),
            "p95": percentile(_numbers(cases, "tool_calls"), 0.95),
        },
        "parallel_ratio": {
            "median": _median(_numbers(cases, "parallel_ratio")),
            "p95": percentile(_numbers(cases, "parallel_ratio"), 0.95),
        },
        "expansion_rounds": {
            "median": _median(_numbers(cases, "expansion_rounds")),
            "p95": percentile(_numbers(cases, "expansion_rounds"), 0.95),
        },
        "response_characters": {
            "median": _median(_numbers(cases, "character_count")),
            "p95": percentile(_numbers(cases, "character_count"), 0.95),
        },
        "estimated_output_tokens": {
            "median": _median(_numbers(cases, "estimated_output_tokens")),
            "p95": percentile(
                _numbers(cases, "estimated_output_tokens"), 0.95
            ),
        },
    }


def _case_ids(cases: Iterable[dict[str, Any]], predicate) -> tuple[str, ...]:
    return tuple(str(case.get("id", "unknown")) for case in cases if predicate(case))


def evaluate_acceptance_gates(
    report: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
    max_tool_calls_p95: float = 12.0,
    max_expansion_rounds_p95: float = 2.0,
    max_latency_regression: float = 0.10,
) -> GateResult:
    """Evaluate accuracy, safety, empty-response and performance gates.

    A latency regression is only rejected when the strict correct-
    investigation rate did not improve.  That makes the quality/performance
    trade-off explicit instead of silently letting tool count grow forever.
    """
    cases = report.get("cases", [])
    if not isinstance(cases, list):
        cases = []
    diagnostics = report.get("diagnostics", {})
    summary = report.get("summary", {})
    runtime = runtime_summary(report)
    violations: list[GateViolation] = []

    mismatches = diagnostics.get("behavioral_mismatches", [])
    if mismatches:
        violations.append(
            GateViolation(
                "accuracy",
                "Behavioral stage mismatches were detected.",
                tuple(str(item.get("id", "unknown")) for item in mismatches),
            )
        )

    empty_ids = _case_ids(cases, lambda case: bool(case.get("response_empty")))
    if empty_ids:
        violations.append(
            GateViolation(
                "response",
                "An HTTP-success path produced an empty response.",
                empty_ids,
            )
        )

    security_ids = _case_ids(
        cases,
        lambda case: _security_gap(case),
    )
    if security_ids:
        violations.append(
            GateViolation(
                "safety",
                "One or more executed tool calls lack a complete security receipt.",
                security_ids,
            )
        )

    tool_p95 = runtime["tool_calls"]["p95"]
    if tool_p95 is not None and tool_p95 > max_tool_calls_p95:
        violations.append(
            GateViolation(
                "tool_budget",
                f"P95 tool calls {tool_p95} exceeds budget {max_tool_calls_p95}.",
            )
        )
    expansion_p95 = runtime["expansion_rounds"]["p95"]
    if expansion_p95 is not None and expansion_p95 > max_expansion_rounds_p95:
        violations.append(
            GateViolation(
                "tool_budget",
                "P95 expansion rounds "
                f"{expansion_p95} exceeds budget {max_expansion_rounds_p95}.",
            )
        )

    if baseline is not None:
        baseline_runtime = runtime_summary(baseline)
        current_p95 = runtime["latency_ms"]["p95"]
        baseline_p95 = baseline_runtime["latency_ms"]["p95"]
        current_accuracy = summary.get("strict_correct_investigation_rate")
        baseline_accuracy = baseline.get("summary", {}).get(
            "strict_correct_investigation_rate"
        )
        if (
            current_p95 is not None
            and baseline_p95 is not None
            and baseline_p95 > 0
            and current_p95 > baseline_p95 * (1 + max_latency_regression)
            and isinstance(current_accuracy, (int, float))
            and isinstance(baseline_accuracy, (int, float))
            and current_accuracy <= baseline_accuracy
        ):
            violations.append(
                GateViolation(
                    "performance",
                    "P95 latency regressed by more than "
                    f"{max_latency_regression:.0%} without an accuracy improvement.",
                )
            )

    metrics = {
        "strict_correct_investigation_rate": summary.get(
            "strict_correct_investigation_rate"
        ),
        "observable_core_accuracy": summary.get("observable_core_accuracy"),
        "runtime": runtime,
        "cases": len(cases),
        "behavioral_mismatch_count": len(mismatches),
        "empty_response_count": len(empty_ids),
        "security_receipt_gap_count": len(security_ids),
    }
    return GateResult(not violations, metrics, tuple(violations))


def _security_gap(case: dict[str, Any]) -> bool:
    metrics = case.get("actual", {}).get("runtime_metrics") or {}
    tool_calls = metrics.get("tool_calls")
    inspected = metrics.get("security_inspections_total")
    if not isinstance(tool_calls, (int, float)) or tool_calls <= 0:
        return False
    return not isinstance(inspected, (int, float)) or inspected < tool_calls


def render_markdown(result: GateResult) -> str:
    """Render a concise human-readable companion to the JSON artifact."""
    status = "PASS" if result.passed else "FAIL"
    metrics = result.metrics
    runtime = metrics["runtime"]
    lines = [
        "# Orion Acceptance Gates",
        "",
        f"- Status: **{status}**",
        f"- Cases: {metrics['cases']}",
        f"- Strict correct investigation rate: {metrics['strict_correct_investigation_rate']}",
        f"- Observable core accuracy: {metrics['observable_core_accuracy']}",
        f"- P95 latency (ms): {runtime['latency_ms']['p95']}",
        f"- P95 tool calls: {runtime['tool_calls']['p95']}",
        f"- P95 expansion rounds: {runtime['expansion_rounds']['p95']}",
        "",
        "## Violations",
        "",
    ]
    if not result.violations:
        lines.append("None.")
    else:
        for violation in result.violations:
            cases = (
                f" (`{', '.join(violation.case_ids)}`)" if violation.case_ids else ""
            )
            lines.append(f"- **{violation.gate}**: {violation.message}{cases}")
    return "\n".join(lines) + "\n"


def write_report(result: GateResult, output_dir: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown acceptance artifacts without overwriting input."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "acceptance_gates.json"
    markdown_path = output_dir / "acceptance_gates.md"
    json_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, markdown_path
