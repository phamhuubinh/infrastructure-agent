#!/usr/bin/env python3
"""Canonical contract baseline runner for Orion.

The runner scores only public canonical runtime behavior:

- terminal decision
- proposed/observed capability ids
- exact target/source references
- successful observations
- action budget
- approval/failure state
- non-empty response

It deliberately does not score deterministic intent parsing, semantic
classifiers, prose target resolution, or hidden model reasoning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.metadata import collect_benchmark_metadata  # noqa: E402
from scripts.qa.build_golden import (  # noqa: E402
    EXPECTED_FIELDS,
    SCHEMA_VERSION,
    GoldenValidationError,
    validate_cases,
)


_CONTRACT_FIELDS = tuple(EXPECTED_FIELDS)


class BaselinePreflightError(RuntimeError):
    """Raised when a meaningful canonical baseline cannot run."""


class _CaseContextStore:
    """Read-only conversation context for one independent QA case."""

    def __init__(
        self,
        messages: list[dict[str, str]],
    ) -> None:
        self._history = [
            dict(message)
            for message in messages
        ]
        self.summarize_fn = None

    @property
    def history(self) -> list[dict[str, str]]:
        return [
            dict(message)
            for message in self._history
        ]

    def add_turn(
        self,
        user: str,
        assistant: str,
    ) -> None:
        # Baseline cases must remain independent.
        del user, assistant

    def set_summarize_fn(
        self,
        fn,
    ) -> None:
        self.summarize_fn = fn


def load_golden_cases(
    path: Path,
) -> list[dict[str, Any]]:
    """Load one canonical golden file or a canonical golden directory."""

    if path.is_dir():
        from scripts.qa.build_golden import (
            load_golden_cases as load_all,
        )

        doc = load_all(path)

        return [
            case
            for case in doc["cases"]
            if not case.get("harness_error")
        ]

    if not path.is_file():
        raise BaselinePreflightError(
            f"Golden dataset not found: {path}"
        )

    loaded = (
        yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )
        or {}
    )

    if (
        not isinstance(loaded, dict)
        or loaded.get("schema_version")
        != SCHEMA_VERSION
    ):
        raise GoldenValidationError(
            f"{path}: expected canonical "
            f"schema_version={SCHEMA_VERSION}"
        )

    groups = loaded.get("groups")
    cases = loaded.get("cases")

    if not isinstance(groups, dict):
        raise GoldenValidationError(
            f"{path}: missing groups"
        )

    if not isinstance(cases, list):
        raise GoldenValidationError(
            f"{path}: missing cases"
        )

    validate_cases(
        cases,
        groups,
        require_coverage=False,
    )

    return [
        case
        for case in cases
        if not case.get("harness_error")
    ]


def _canonical_metrics(
    result: Mapping[str, object],
) -> dict[str, object]:
    trace = result.get(
        "execution_trace"
    )

    if not isinstance(trace, Mapping):
        return {}

    runtime_metrics = trace.get(
        "runtime_metrics"
    )

    if not isinstance(
        runtime_metrics,
        Mapping,
    ):
        return {}

    canonical = runtime_metrics.get(
        "canonical_runtime"
    )

    if not isinstance(
        canonical,
        Mapping,
    ):
        return {}

    return dict(canonical)


def extract_actual(
    result: Mapping[str, object],
) -> dict[str, Any]:
    """Project public session-agent output into canonical QA observations."""

    canonical = _canonical_metrics(
        result
    )

    capabilities: list[str] = []
    references: list[str] = []
    successful = 0

    raw_steps = result.get("steps")

    if isinstance(raw_steps, list):
        for step in raw_steps:
            if not isinstance(
                step,
                Mapping,
            ):
                continue

            capability = step.get(
                "capability_id"
            )

            if (
                isinstance(
                    capability,
                    str,
                )
                and capability
                and capability
                not in capabilities
            ):
                capabilities.append(
                    capability
                )

            for key in (
                "target_id",
                "source_id",
            ):
                reference = step.get(key)

                if (
                    isinstance(
                        reference,
                        str,
                    )
                    and reference
                    and reference
                    not in references
                ):
                    references.append(
                        reference
                    )

            if step.get("status") == "success":
                successful += 1

    response = result.get("response")

    response_present = (
        isinstance(response, str)
        and bool(response.strip())
    )

    budget = canonical.get("budget")

    if not isinstance(
        budget,
        Mapping,
    ):
        budget = {}

    action_attempts = canonical.get(
        "action_attempts"
    )

    if (
        type(action_attempts) is not int
        or action_attempts < 0
    ):
        action_attempts = 0

    tool_calls = budget.get(
        "actions_used"
    )

    if (
        type(tool_calls) is not int
        or tool_calls < 0
    ):
        tool_calls = 0

    def _non_negative_int(
        key: str,
    ) -> int:
        value = canonical.get(key)

        if (
            type(value) is int
            and value >= 0
        ):
            return value

        return 0

    return {
        "terminal": canonical.get(
            "terminal"
        )
        or "runner_exception",
        "capabilities": capabilities,
        "references": references,
        "successful_observations": (
            successful
        ),
        "action_attempts": (
            action_attempts
        ),
        "approval_required": bool(
            canonical.get(
                "approval_required",
                False,
            )
        ),
        "failure": canonical.get(
            "failure"
        ),
        "response_present": (
            response_present
        ),
        "runtime_metrics": {
            "model_calls": (
                _non_negative_int(
                    "model_calls"
                )
            ),
            "discovery_calls": (
                _non_negative_int(
                    "discovery_calls"
                )
            ),
            "action_attempts": (
                action_attempts
            ),
            "observation_count": (
                _non_negative_int(
                    "observation_count"
                )
            ),
            "tool_calls": tool_calls,
        },
    }


def _field_status(
    field: str,
    expected: Any,
    actual: dict[str, Any],
) -> str:
    capabilities = actual[
        "capabilities"
    ]
    references = actual[
        "references"
    ]

    if field == "terminals":
        matched = (
            actual["terminal"]
            in expected
        )

    elif (
        field
        == "required_capability_sets"
    ):
        matched = all(
            any(
                capability
                in capabilities
                for capability
                in alternatives
            )
            for alternatives
            in expected
        )

    elif (
        field
        == "required_capability_prefixes"
    ):
        matched = all(
            any(
                capability.startswith(
                    prefix
                )
                for capability
                in capabilities
            )
            for prefix in expected
        )

    elif (
        field
        == "forbidden_capability_prefixes"
    ):
        matched = all(
            not any(
                capability.startswith(
                    prefix
                )
                for capability
                in capabilities
            )
            for prefix in expected
        )

    elif field == "required_references":
        matched = all(
            reference in references
            for reference in expected
        )

    elif field == "forbidden_references":
        matched = all(
            reference not in references
            for reference in expected
        )

    elif (
        field
        == "min_successful_observations"
    ):
        matched = (
            actual[
                "successful_observations"
            ]
            >= expected
        )

    elif field == "max_actions":
        matched = (
            actual["action_attempts"]
            <= expected
        )

    elif field == "approval_required":
        matched = (
            actual["approval_required"]
            is expected
        )

    elif field == "failure":
        matched = (
            actual["failure"]
            == expected
        )

    elif field == "response_required":
        matched = (
            actual["response_present"]
            is expected
        )

    else:
        raise ValueError(
            f"Unknown canonical contract field: {field}"
        )

    return (
        "match"
        if matched
        else "mismatch"
    )


def score_case(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> dict[str, Any]:
    field_status = {
        field: _field_status(
            field,
            expected[field],
            actual,
        )
        for field
        in _CONTRACT_FIELDS
    }

    contract_pass = all(
        value == "match"
        for value
        in field_status.values()
    )

    return {
        "field_status": field_status,
        "contract_pass": (
            contract_pass
        ),
        "expected": expected,
        "actual": actual,
    }


def _config_hash(
    project_root: Path,
) -> str:
    digest = hashlib.sha256()
    found = False

    for name in (
        "targets.json",
        "servers.json",
    ):
        path = project_root / name

        if path.is_file():
            digest.update(
                path.read_bytes()
            )
            found = True

    return (
        digest.hexdigest()[:16]
        if found
        else "unknown"
    )


def _resolve_model_context(
    server_name: str | None,
) -> dict[str, Any]:
    from src.shared.config import get_config

    config = get_config()

    if not config.servers:
        return {
            "configured": False,
            "server_name": "",
            "model": "",
            "provider": "",
        }

    resolved_name = (
        server_name
        or config.active_server_name
    )

    if not resolved_name:
        raise BaselinePreflightError(
            "servers.json has model servers "
            "but no active server; pass "
            "--server explicitly."
        )

    if resolved_name not in config.servers:
        available = ", ".join(
            sorted(config.servers)
        )

        raise BaselinePreflightError(
            f"Model server {resolved_name!r} "
            "is not configured. "
            f"Available: {available or '(none)'}."
        )

    raw = config.servers[
        resolved_name
    ]

    return {
        "configured": True,
        "server_name": resolved_name,
        "model": str(
            raw.get("model", "")
        ),
        "provider": str(
            raw.get("provider", "")
        ),
    }


def _runner_exception_result(
    exc: Exception,
) -> dict[str, Any]:
    return {
        "response": "",
        "steps": [],
        "investigation": None,
        "trace_id": None,
        "execution_trace": {
            "trace_id": None,
            "user_request": "",
            "answer_strategy": (
                "CANONICAL_AGENT"
            ),
            "routing_status": (
                "runner_exception"
            ),
            "evidence_status": (
                "not_applicable"
            ),
            "response_strategy": (
                "runner_exception"
            ),
            "runtime_metrics": {
                "canonical_runtime": {
                    "terminal": (
                        "runner_exception"
                    ),
                    "model_calls": 0,
                    "discovery_calls": 0,
                    "action_attempts": 0,
                    "observation_count": 0,
                    "failure": (
                        "runner_exception"
                    ),
                    "approval_required": (
                        False
                    ),
                    "budget": {
                        "max_actions": 0,
                        "actions_used": 0,
                        "max_cost": 0,
                        "cost_used": 0,
                    },
                }
            },
        },
        "_runner_error": str(exc)[
            :500
        ],
    }


def _apply_case_context(
    agent: object,
    case: Mapping[str, object],
) -> None:
    raw = case.get("context")

    if raw is None:
        context_store = None

    elif isinstance(raw, list):
        context_store = (
            _CaseContextStore(
                [
                    dict(message)
                    for message in raw
                    if isinstance(
                        message,
                        dict,
                    )
                ]
            )
        )

    else:
        raise ValueError(
            "case context must be a list"
        )

    try:
        setattr(
            agent,
            "conversation_store",
            context_store,
        )
    except (AttributeError, TypeError):
        if context_store is not None:
            raise BaselinePreflightError(
                "Injected agent does not "
                "support canonical case context."
            )


def run_baseline(
    golden_path: Path,
    server_name: str | None,
    target_store_path: str,
    *,
    smoke: bool = False,
    health_timeout: float = 5.0,
    agent_factory: (
        Callable[..., Any] | None
    ) = None,
) -> dict[str, Any]:
    """Run independent canonical golden cases through one agent graph."""

    cases = load_golden_cases(
        golden_path
    )

    model_context = (
        _resolve_model_context(
            server_name
        )
    )

    if (
        not smoke
        and not model_context[
            "configured"
        ]
    ):
        raise BaselinePreflightError(
            "No model is configured. "
            "Configure a model or use "
            "--smoke for a non-meaningful "
            "setup-mode run."
        )

    if agent_factory is None:
        from src.agent.canonical_factory import (
            create_canonical_session_agent,
        )

        agent_factory = (
            create_canonical_session_agent
        )

    effective_server = (
        model_context["server_name"]
        or None
    )

    if smoke:
        from src.model.unconfigured_adapter import (
            UnconfiguredAssessmentAdapter,
        )

        agent = agent_factory(
            target_store_path=(
                target_store_path
            ),
            server_name=None,
            assessment_adapter=(
                UnconfiguredAssessmentAdapter()
            ),
        )

        model_health_ok: (
            bool | None
        ) = None

    else:
        agent = agent_factory(
            target_store_path=(
                target_store_path
            ),
            server_name=(
                effective_server
            ),
        )

        model_health_ok = bool(
            agent.health_check(
                timeout=health_timeout
            )
        )

        if not model_health_ok:
            raise BaselinePreflightError(
                f"Configured model server "
                f"{effective_server!r} failed "
                "its health check."
            )

    case_reports: list[
        dict[str, Any]
    ] = []

    for case in cases:
        _apply_case_context(
            agent,
            case,
        )

        started = time.perf_counter()

        try:
            result = agent.run_with_steps(
                case["question"]
            )
            error = None
        except Exception as exc:
            result = (
                _runner_exception_result(
                    exc
                )
            )
            error = str(exc)[:500]

        elapsed_ms = round(
            (
                time.perf_counter()
                - started
            )
            * 1000,
            3,
        )

        actual = extract_actual(
            result
        )

        scored = score_case(
            case["expected"],
            actual,
        )

        response = result.get(
            "response"
        )

        response_character_count = (
            len(response)
            if isinstance(
                response,
                str,
            )
            else 0
        )

        case_reports.append(
            {
                "id": case["id"],
                "group": case["group"],
                "question": (
                    case["question"]
                ),
                "tags": case.get(
                    "tags",
                    [],
                ),
                "error": error,
                "elapsed_ms": (
                    elapsed_ms
                ),
                "response_empty": (
                    response_character_count
                    == 0
                ),
                "response_character_count": (
                    response_character_count
                ),
                **scored,
            }
        )

    run_context = {
        "run_mode": (
            "smoke"
            if smoke
            else "baseline"
        ),
        "baseline_status": (
            "smoke_only"
            if smoke
            else "completed"
        ),
        "meaningful_baseline": (
            not smoke
            and bool(model_health_ok)
        ),
        "model_configured": bool(
            model_context[
                "configured"
            ]
        ),
        "model_health_ok": (
            model_health_ok
        ),
        "resolved_server": (
            effective_server or ""
        ),
        "resolved_model": (
            model_context["model"]
        ),
        "resolved_provider": (
            model_context["provider"]
        ),
    }

    return _summarize(
        cases,
        case_reports,
        golden_path,
        effective_server,
        run_context=run_context,
    )


def _summarize(
    cases: list[dict[str, Any]],
    case_reports: list[
        dict[str, Any]
    ],
    golden_path: Path,
    server_name: str | None,
    *,
    run_context: (
        dict[str, Any] | None
    ) = None,
) -> dict[str, Any]:
    del cases

    context = run_context or {
        "run_mode": "baseline",
        "baseline_status": (
            "completed"
        ),
        "meaningful_baseline": True,
        "model_configured": True,
        "model_health_ok": True,
        "resolved_server": (
            server_name or ""
        ),
        "resolved_model": "",
        "resolved_provider": "",
    }

    total = len(case_reports)

    passed = sum(
        1
        for report in case_reports
        if report["contract_pass"]
    )

    strict_rate = (
        round(
            passed / total,
            4,
        )
        if total
        else 0.0
    )

    meaningful = bool(
        context[
            "meaningful_baseline"
        ]
    )

    field_accuracy: dict[
        str,
        dict[str, Any],
    ] = {}

    for field in _CONTRACT_FIELDS:
        match = sum(
            1
            for report in case_reports
            if report[
                "field_status"
            ][field]
            == "match"
        )

        mismatch = total - match

        field_accuracy[field] = {
            "match": match,
            "mismatch": mismatch,
            "accuracy": (
                round(
                    match / total,
                    4,
                )
                if total
                else 0.0
            ),
        }

    def _bucket(
        labels: Callable[
            [dict[str, Any]],
            list[str],
        ],
    ) -> dict[str, dict[str, Any]]:
        buckets: dict[
            str,
            dict[str, int],
        ] = {}

        for report in case_reports:
            for label in labels(report):
                stats = buckets.setdefault(
                    label,
                    {
                        "total": 0,
                        "passed": 0,
                    },
                )

                stats["total"] += 1

                if report[
                    "contract_pass"
                ]:
                    stats["passed"] += 1

        result: dict[
            str,
            dict[str, Any],
        ] = {}

        for label, stats in (
            buckets.items()
        ):
            result[label] = {
                **stats,
                "strict_canonical_contract_rate": (
                    round(
                        stats["passed"]
                        / stats["total"],
                        4,
                    )
                ),
            }

        return result

    by_group = _bucket(
        lambda report: [
            str(report["group"])
        ]
    )

    by_tag = _bucket(
        lambda report: [
            str(tag)
            for tag
            in report.get(
                "tags",
                [],
            )
        ]
    )

    def _language(
        report: dict[str, Any],
    ) -> list[str]:
        tags = [
            str(tag)
            for tag
            in report.get(
                "tags",
                [],
            )
        ]

        if any(
            "code-switch"
            in tag
            for tag in tags
        ):
            return ["code-switch"]

        if any(
            tag.startswith("vi")
            for tag in tags
        ):
            return ["vi"]

        if any(
            tag.startswith("en")
            for tag in tags
        ):
            return ["en"]

        return ["other"]

    by_language = _bucket(
        _language
    )

    durations = sorted(
        float(
            report["elapsed_ms"]
        )
        for report in case_reports
    )

    median_ms = (
        durations[
            len(durations) // 2
        ]
        if durations
        else None
    )

    p95_ms = (
        durations[
            min(
                int(
                    len(durations)
                    * 0.95
                ),
                len(durations) - 1,
            )
        ]
        if durations
        else None
    )

    metadata = (
        collect_benchmark_metadata(
            server_name=server_name
        )
    )

    if context.get(
        "resolved_model"
    ):
        metadata["model"] = (
            context[
                "resolved_model"
            ]
        )

    if context.get(
        "resolved_provider"
    ):
        metadata["provider"] = (
            context[
                "resolved_provider"
            ]
        )

    metadata.update(context)

    metadata["config_hash"] = (
        _config_hash(
            PROJECT_ROOT
        )
    )
    metadata[
        "golden_schema_version"
    ] = SCHEMA_VERSION
    metadata[
        "golden_dataset_path"
    ] = str(golden_path)
    metadata[
        "golden_dataset_cases_total"
    ] = total

    mismatches = [
        {
            "id": report["id"],
            "group": (
                report["group"]
            ),
            "fields": [
                field
                for field, status
                in report[
                    "field_status"
                ].items()
                if status
                == "mismatch"
            ],
        }
        for report in case_reports
        if not report[
            "contract_pass"
        ]
    ]

    return {
        "metadata": metadata,
        "summary": {
            "cases_total": total,
            "cases_passed": passed,
            "canonical_contract_rate": (
                strict_rate
                if meaningful
                else None
            ),
            "strict_canonical_contract_rate": (
                strict_rate
            ),
            "field_accuracy": (
                field_accuracy
            ),
            "by_group": by_group,
            "by_tag": by_tag,
            "by_language": (
                by_language
            ),
            "latency_ms": {
                "median": median_ms,
                "p95": p95_ms,
            },
        },
        "diagnostics": {
            "behavioral_mismatches": (
                mismatches
            ),
        },
        "cases": case_reports,
    }


def render_markdown(
    report: dict[str, Any],
) -> str:
    metadata = report[
        "metadata"
    ]
    summary = report["summary"]

    meaningful = bool(
        metadata.get(
            "meaningful_baseline"
        )
    )

    def pct(
        value: float | None,
    ) -> str:
        return (
            f"{value:.2%}"
            if value is not None
            else "n/a"
        )

    lines = [
        "# Orion Canonical QA Baseline",
        "",
        (
            "- Golden schema: "
            f"{metadata.get('golden_schema_version')}"
        ),
        (
            "- Run mode: "
            f"{metadata.get('run_mode')}"
        ),
        (
            "- Meaningful baseline: "
            f"{str(meaningful).lower()}"
        ),
        (
            "- Commit: "
            f"{metadata.get('git_commit', 'unknown')}"
        ),
        (
            "- Config hash: "
            f"{metadata.get('config_hash', 'unknown')}"
        ),
        "",
    ]

    if meaningful:
        lines += [
            (
                "## Headline: "
                "canonical_contract_rate = "
                f"{pct(summary['canonical_contract_rate'])}"
            ),
            "",
        ]
    else:
        lines += [
            (
                "## Smoke run — "
                "not a meaningful baseline"
            ),
            "",
            (
                "`canonical_contract_rate` "
                "is intentionally not published."
            ),
            "",
        ]

    lines += [
        "## Metrics",
        "",
        (
            "- strict_canonical_contract_rate: "
            f"{pct(summary['strict_canonical_contract_rate'])}"
        ),
        "",
        "## Contract field accuracy",
        "",
        "| Field | Match | Mismatch | Accuracy |",
        "|---|---:|---:|---:|",
    ]

    for field, stats in (
        summary[
            "field_accuracy"
        ].items()
    ):
        lines.append(
            f"| {field} | "
            f"{stats['match']} | "
            f"{stats['mismatch']} | "
            f"{pct(stats['accuracy'])} |"
        )

    lines += [
        "",
        "## By group",
        "",
        "| Group | Cases | Rate |",
        "|---|---:|---:|",
    ]

    for group in sorted(
        summary["by_group"]
    ):
        stats = summary[
            "by_group"
        ][group]

        lines.append(
            f"| {group} | "
            f"{stats['total']} | "
            f"{pct(stats['strict_canonical_contract_rate'])} |"
        )

    lines += [
        "",
        "## Latency",
        "",
        (
            "- median elapsed_ms: "
            f"{summary['latency_ms']['median']}"
        ),
        (
            "- p95 elapsed_ms: "
            f"{summary['latency_ms']['p95']}"
        ),
        "",
        "## Canonical contract mismatches",
        "",
    ]

    mismatches = report[
        "diagnostics"
    ]["behavioral_mismatches"]

    if not mismatches:
        lines.append("None.")
    else:
        for mismatch in mismatches:
            lines.append(
                f"- `{mismatch['id']}` "
                f"({mismatch['group']}): "
                f"{mismatch['fields']}"
            )

    return "\n".join(lines) + "\n"


def _write_report(
    report: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    suffix = (
        "smoke"
        if report["metadata"][
            "run_mode"
        ]
        == "smoke"
        else "baseline"
    )

    json_path = (
        output_dir
        / f"{suffix}_{stamp}.json"
    )

    md_path = (
        output_dir
        / f"{suffix}_{stamp}.md"
    )

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path.write_text(
        render_markdown(report),
        encoding="utf-8",
    )

    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Canonical Orion QA baseline."
        )
    )

    parser.add_argument(
        "--golden",
        default=str(
            PROJECT_ROOT
            / "tests"
            / "data"
            / "qa_cases"
            / "golden_core.yaml"
        ),
    )

    parser.add_argument(
        "--output-dir",
        default=str(
            PROJECT_ROOT
            / "benchmark_results"
        ),
    )

    parser.add_argument(
        "--server",
        default=None,
    )

    parser.add_argument(
        "--target-store",
        default=str(
            PROJECT_ROOT
            / "targets.json"
        ),
    )

    parser.add_argument(
        "--smoke",
        action="store_true",
    )

    parser.add_argument(
        "--health-timeout",
        type=float,
        default=5.0,
    )

    args = parser.parse_args()

    try:
        report = run_baseline(
            Path(args.golden),
            args.server,
            args.target_store,
            smoke=args.smoke,
            health_timeout=(
                args.health_timeout
            ),
        )
    except (
        BaselinePreflightError,
        GoldenValidationError,
        ValueError,
        OSError,
    ) as exc:
        print(
            f"Baseline not run: {exc}",
            file=sys.stderr,
        )
        return 2

    json_path, md_path = (
        _write_report(
            report,
            Path(args.output_dir),
        )
    )

    print(
        f"Report JSON: {json_path}"
    )
    print(
        f"Report Markdown: {md_path}"
    )

    if report["metadata"][
        "meaningful_baseline"
    ]:
        print(
            "canonical_contract_rate: "
            f"{report['summary']['canonical_contract_rate']:.2%}"
        )
    else:
        print(
            "Smoke run only; "
            "canonical_contract_rate "
            "was not published."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
