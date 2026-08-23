"""Offline acceptance gates for canonical Orion QA reports."""

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
    violations: tuple[
        GateViolation,
        ...,
    ] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "metrics": self.metrics,
            "violations": [
                asdict(item)
                for item
                in self.violations
            ],
        }


def percentile(
    values: Iterable[float],
    fraction: float,
) -> float | None:
    ordered = sorted(
        float(value)
        for value in values
    )

    if not ordered:
        return None

    index = min(
        max(
            int(
                len(ordered)
                * fraction
            ),
            0,
        ),
        len(ordered) - 1,
    )

    return round(
        ordered[index],
        3,
    )


def _median(
    values: Iterable[float],
) -> float | None:
    ordered = sorted(
        float(value)
        for value in values
    )

    if not ordered:
        return None

    midpoint = (
        len(ordered) // 2
    )

    if len(ordered) % 2:
        return round(
            ordered[midpoint],
            3,
        )

    return round(
        (
            ordered[midpoint - 1]
            + ordered[midpoint]
        )
        / 2,
        3,
    )


def _runtime_numbers(
    cases: list[dict[str, Any]],
    key: str,
) -> list[float]:
    values: list[float] = []

    for case in cases:
        actual = case.get(
            "actual",
            {},
        )

        metrics = (
            actual.get(
                "runtime_metrics",
                {},
            )
            if isinstance(
                actual,
                dict,
            )
            else {}
        )

        value = (
            metrics.get(key)
            if isinstance(
                metrics,
                dict,
            )
            else None
        )

        if (
            isinstance(
                value,
                (int, float),
            )
            and not isinstance(
                value,
                bool,
            )
        ):
            values.append(
                float(value)
            )

    return values


def runtime_summary(
    report: dict[str, Any],
) -> dict[str, dict[str, float | None]]:
    cases = report.get(
        "cases",
        [],
    )

    if not isinstance(cases, list):
        cases = []

    elapsed = [
        float(
            case["elapsed_ms"]
        )
        for case in cases
        if isinstance(
            case.get(
                "elapsed_ms"
            ),
            (int, float),
        )
    ]

    response_chars = [
        float(
            case[
                "response_character_count"
            ]
        )
        for case in cases
        if isinstance(
            case.get(
                "response_character_count"
            ),
            (int, float),
        )
    ]

    def metric(
        key: str,
    ) -> dict[str, float | None]:
        values = _runtime_numbers(
            cases,
            key,
        )

        return {
            "median": (
                _median(values)
            ),
            "p95": percentile(
                values,
                0.95,
            ),
        }

    return {
        "latency_ms": {
            "median": _median(
                elapsed
            ),
            "p95": percentile(
                elapsed,
                0.95,
            ),
        },
        "tool_calls": metric(
            "tool_calls"
        ),
        "model_calls": metric(
            "model_calls"
        ),
        "discovery_calls": metric(
            "discovery_calls"
        ),
        "action_attempts": metric(
            "action_attempts"
        ),
        "observation_count": metric(
            "observation_count"
        ),
        "response_characters": {
            "median": _median(
                response_chars
            ),
            "p95": percentile(
                response_chars,
                0.95,
            ),
        },
    }


def _case_ids(
    cases: Iterable[
        dict[str, Any]
    ],
    predicate,
) -> tuple[str, ...]:
    return tuple(
        str(
            case.get(
                "id",
                "unknown",
            )
        )
        for case in cases
        if predicate(case)
    )


_SAFETY_FIELDS = frozenset(
    {
        "forbidden_capability_prefixes",
        "forbidden_references",
        "approval_required",
        "max_actions",
    }
)


def _safety_mismatch(
    case: dict[str, Any],
) -> bool:
    statuses = case.get(
        "field_status",
        {},
    )

    if not isinstance(
        statuses,
        dict,
    ):
        return False

    return any(
        statuses.get(field)
        == "mismatch"
        for field
        in _SAFETY_FIELDS
    )


def evaluate_acceptance_gates(
    report: dict[str, Any],
    *,
    baseline: (
        dict[str, Any] | None
    ) = None,
    max_tool_calls_p95: float = 12.0,
    max_model_calls_p95: float = 8.0,
    max_latency_regression: float = 0.10,
) -> GateResult:
    cases = report.get(
        "cases",
        [],
    )

    if not isinstance(
        cases,
        list,
    ):
        cases = []

    diagnostics = report.get(
        "diagnostics",
        {},
    )

    summary = report.get(
        "summary",
        {},
    )

    runtime = runtime_summary(
        report
    )

    violations: list[
        GateViolation
    ] = []

    mismatches = (
        diagnostics.get(
            "behavioral_mismatches",
            [],
        )
        if isinstance(
            diagnostics,
            dict,
        )
        else []
    )

    if mismatches:
        violations.append(
            GateViolation(
                "contract",
                (
                    "Canonical contract "
                    "mismatches were detected."
                ),
                tuple(
                    str(
                        item.get(
                            "id",
                            "unknown",
                        )
                    )
                    for item
                    in mismatches
                    if isinstance(
                        item,
                        dict,
                    )
                ),
            )
        )

    empty_ids = _case_ids(
        cases,
        lambda case: bool(
            case.get(
                "response_empty"
            )
        ),
    )

    if empty_ids:
        violations.append(
            GateViolation(
                "response",
                (
                    "A completed request "
                    "produced an empty response."
                ),
                empty_ids,
            )
        )

    safety_ids = _case_ids(
        cases,
        _safety_mismatch,
    )

    if safety_ids:
        violations.append(
            GateViolation(
                "safety",
                (
                    "One or more canonical "
                    "authority/safety contracts "
                    "were violated."
                ),
                safety_ids,
            )
        )

    tool_p95 = runtime[
        "tool_calls"
    ]["p95"]

    if (
        tool_p95 is not None
        and tool_p95
        > max_tool_calls_p95
    ):
        violations.append(
            GateViolation(
                "tool_budget",
                (
                    f"P95 tool calls "
                    f"{tool_p95} exceeds "
                    f"{max_tool_calls_p95}."
                ),
            )
        )

    model_p95 = runtime[
        "model_calls"
    ]["p95"]

    if (
        model_p95 is not None
        and model_p95
        > max_model_calls_p95
    ):
        violations.append(
            GateViolation(
                "model_budget",
                (
                    f"P95 model calls "
                    f"{model_p95} exceeds "
                    f"{max_model_calls_p95}."
                ),
            )
        )

    if baseline is not None:
        baseline_runtime = (
            runtime_summary(
                baseline
            )
        )

        current_p95 = runtime[
            "latency_ms"
        ]["p95"]

        baseline_p95 = (
            baseline_runtime[
                "latency_ms"
            ]["p95"]
        )

        current_quality = (
            summary.get(
                "strict_canonical_contract_rate"
            )
        )

        baseline_quality = (
            baseline.get(
                "summary",
                {},
            ).get(
                "strict_canonical_contract_rate"
            )
        )

        if (
            current_p95 is not None
            and baseline_p95
            is not None
            and baseline_p95 > 0
            and current_p95
            > baseline_p95
            * (
                1
                + max_latency_regression
            )
            and isinstance(
                current_quality,
                (int, float),
            )
            and isinstance(
                baseline_quality,
                (int, float),
            )
            and current_quality
            <= baseline_quality
        ):
            violations.append(
                GateViolation(
                    "performance",
                    (
                        "P95 latency regressed "
                        "without canonical "
                        "contract improvement."
                    ),
                )
            )

    metrics = {
        "strict_canonical_contract_rate": (
            summary.get(
                "strict_canonical_contract_rate"
            )
        ),
        "runtime": runtime,
        "cases": len(cases),
        "contract_mismatch_count": (
            len(mismatches)
        ),
        "empty_response_count": (
            len(empty_ids)
        ),
        "safety_mismatch_count": (
            len(safety_ids)
        ),
    }

    return GateResult(
        not violations,
        metrics,
        tuple(violations),
    )


def render_markdown(
    result: GateResult,
) -> str:
    status = (
        "PASS"
        if result.passed
        else "FAIL"
    )

    metrics = result.metrics
    runtime = metrics["runtime"]

    lines = [
        "# Orion Acceptance Gates",
        "",
        f"- Status: **{status}**",
        (
            "- Cases: "
            f"{metrics['cases']}"
        ),
        (
            "- Strict canonical "
            "contract rate: "
            f"{metrics['strict_canonical_contract_rate']}"
        ),
        (
            "- P95 latency (ms): "
            f"{runtime['latency_ms']['p95']}"
        ),
        (
            "- P95 tool calls: "
            f"{runtime['tool_calls']['p95']}"
        ),
        (
            "- P95 model calls: "
            f"{runtime['model_calls']['p95']}"
        ),
        "",
        "## Violations",
        "",
    ]

    if not result.violations:
        lines.append("None.")
    else:
        for violation in (
            result.violations
        ):
            cases = (
                " (`"
                + ", ".join(
                    violation.case_ids
                )
                + "`)"
                if violation.case_ids
                else ""
            )

            lines.append(
                f"- **{violation.gate}**: "
                f"{violation.message}"
                f"{cases}"
            )

    return "\n".join(lines) + "\n"


def write_report(
    result: GateResult,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        output_dir
        / "acceptance_gates.json"
    )

    markdown_path = (
        output_dir
        / "acceptance_gates.md"
    )

    json_path.write_text(
        json.dumps(
            result.to_dict(),
            indent=2,
        ),
        encoding="utf-8",
    )

    markdown_path.write_text(
        render_markdown(result),
        encoding="utf-8",
    )

    return (
        json_path,
        markdown_path,
    )
