#!/usr/bin/env python3
"""DR1-005 — Stage-level baseline metrics runner for Orion.

The default mode requires a configured and reachable assessment model.  This
prevents an unconfigured setup-mode run from being written as a meaningful
0% baseline.

Use ``--smoke`` to exercise the runner and deterministic pipeline without a
model.  Smoke reports are explicitly marked ``meaningful_baseline: false``
and do not publish ``correct_investigation_rate`` as a baseline headline.

Each field is scored tri-state: "match" / "mismatch" / "not_observable".
A field is "not_observable" when the pipeline structurally short-circuited
(chat routing, unknown target, a bare pipeline exception, or a runner-level
exception) or when a trace value was simply never set — never a fabricated
comparison. See the comment block above `score_case` for the exact rules.
`strict_correct_investigation_rate` keeps the original, unchanged bar (all
core fields must be "match"); `observable_core_accuracy` and
`trace_completeness_rate` give a fairer read on what the pipeline actually
got right versus what the trace simply doesn't expose yet.

Usage:
    python3 scripts/qa/run_baseline.py
    python3 scripts/qa/run_baseline.py --server sv1
    python3 scripts/qa/run_baseline.py --smoke
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import yaml  # noqa: E402

from benchmark.metadata import collect_benchmark_metadata  # noqa: E402

_CORE_FIELDS = (
    "concepts",
    "operation",
    "intent",
    "target",
    "answer_type",
    "answer_strategy",
    "llm_usage_reason",
)

_STATUS_FIELDS = ("routing_status", "evidence_status")
_APPROXIMATE_FIELDS: tuple[str, ...] = ()
_ALL_SCORED_FIELDS = _CORE_FIELDS + _STATUS_FIELDS + (
    "params",
    "required_evidence",
)


class BaselinePreflightError(RuntimeError):
    """Raised when a meaningful baseline cannot be started safely."""


def load_golden_cases(path: Path) -> list[dict[str, Any]]:
    """Load scorable golden cases, skipping ``harness_error`` entries."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Golden dataset must contain a YAML object: {path}")
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError(f"Golden dataset 'cases' must be a list: {path}")
    return [
        case
        for case in cases
        if isinstance(case, dict) and not case.get("harness_error", False)
    ]


def _enum_name(value: Any) -> str | None:
    """Return ``.name`` for an Enum member, otherwise the value itself."""
    if value is None:
        return None
    return getattr(value, "name", value)


def _derive_routing_status(
    investigation: Any,
    trace_dict: dict[str, Any],
) -> str:
    """Read canonical routing status, with fallback for historical results."""
    canonical = trace_dict.get("routing_status") or _enum_name(
        getattr(investigation, "routing_status", None)
    )
    if canonical:
        return str(canonical).lower()
    failure_stage = trace_dict.get("failure_stage")
    answer_strategy = trace_dict.get("answer_strategy")

    if investigation is None:
        if failure_stage == "target":
            return "unsupported"
        if failure_stage == "pipeline":
            return "fallback"
        return "chat"
    if answer_strategy == "CLARIFICATION":
        return "clarification_required"
    return "resolved"


def _derive_evidence_status(
    investigation: Any,
    trace_dict: dict[str, Any],
) -> str:
    """Read canonical evidence status, with fallback for historical results."""
    canonical = trace_dict.get("evidence_status") or _enum_name(
        getattr(investigation, "evidence_status", None)
    )
    if canonical:
        return str(canonical).lower()
    if investigation is None:
        return "not_applicable"
    if not getattr(investigation, "required_evidence", None):
        return "not_applicable"
    if getattr(investigation, "evidence_complete", False):
        return "sufficient"
    if getattr(investigation, "evidence", None):
        return "partial"
    return "unavailable"


def extract_actual(result: dict[str, Any]) -> dict[str, Any]:
    """Extract a golden-expected-shaped record from ``run_with_steps``."""
    investigation = result.get("investigation")
    trace_dict = result.get("execution_trace") or {}

    semantic = (
        getattr(investigation, "request_frame", None)
        or getattr(investigation, "semantic_request", None)
        if investigation
        else None
    )
    traced_frame = trace_dict.get("actual_request_frame") or {}
    concepts = (
        list(getattr(semantic, "concepts", ()))
        if semantic is not None
        else list(traced_frame.get("concepts", ()))
    )
    if not concepts and semantic is not None:
        concept = getattr(semantic, "concept", None)
        concepts = [concept] if concept else []
    operation = (
        getattr(semantic, "operation", None)
        or getattr(semantic, "action", None)
        if semantic is not None
        else traced_frame.get("operation")
    )

    params: dict[str, str] = {}
    extracted = (
        getattr(investigation, "extracted_params", None) if investigation else None
    )
    to_dict = getattr(extracted, "to_dict", None)
    if callable(to_dict):
        try:
            raw_params = to_dict()
            if isinstance(raw_params, dict):
                params = raw_params
        except Exception:
            params = {}
    elif isinstance(traced_frame.get("parameters"), dict):
        params = traced_frame["parameters"]

    required_evidence: list[str] = []
    if investigation is not None:
        required_evidence = [
            req.name for req in getattr(investigation, "required_evidence", [])
        ]

    return {
        "concepts": concepts,
        "operation": operation,
        "intent": (
            _enum_name(getattr(investigation, "intent", None))
            if investigation
            else None
        ),
        "target": (
            semantic.target_raw
            if semantic is not None and hasattr(semantic, "target_raw")
            else (getattr(investigation, "target", None) if investigation else None)
        ),
        "params": params,
        "answer_type": (
            _enum_name(getattr(investigation, "answer_type", None))
            if investigation
            else trace_dict.get("request_class")
        ),
        "routing_status": _derive_routing_status(investigation, trace_dict),
        "evidence_status": _derive_evidence_status(investigation, trace_dict),
        "answer_strategy": trace_dict.get("answer_strategy"),
        "llm_usage_reason": trace_dict.get("llm_usage_reason"),
        "required_evidence": required_evidence,
        "total_duration_ms": trace_dict.get("total_duration_ms"),
        "runtime_metrics": trace_dict.get("runtime_metrics"),
        "_context": investigation_context(investigation, trace_dict),
    }


# --- Tri-state field scoring (match / mismatch / not_observable) ----------
#
# `investigation is None` happens for THREE structurally different reasons
# (verified directly against src/agent/deterministic_agent.py:run_with_steps):
#
#   1. "chat"                — `_should_pipeline()` was False. The pipeline
#      never ran at all. `execution_trace` is `None` in the raw result (not
#      just missing fields). concepts/operation/intent/target/params/
#      answer_type/required_evidence are correctly empty (nothing to find),
#      so they are scored normally against golden's null/[] expectations.
#      answer_strategy/llm_usage_reason are genuinely absent from the trace
#      (there is no trace) — these must be `not_observable`, not compared.
#
#   2. "target_shortcircuit" — `UnknownTargetError` was raised. Per the real
#      pipeline order (Normalizer -> ParameterExtractor -> AnswerType
#      Classifier -> IntentResolver -> TargetResolver -> ...), concept/
#      operation/intent/answer_type/params WERE computed internally before
#      the exception, but the partial `investigation` is discarded, so we
#      cannot observe what they were -> `not_observable`, not a mismatch
#      against golden's expectation. `target` stays observable (None is the
#      real, meaningful signal: target genuinely didn't resolve).
#      `llm_usage_reason=NONE` IS explicitly set on this path and is
#      observable; `answer_strategy` is left unset -> not_observable via the
#      generic "missing trace value" rule below.
#
#   3. "pipeline_shortcircuit" — a bare `Exception` during pipeline
#      execution. Unlike (2), this is NOT a structured short-circuit: we do
#      not know how far the pipeline got, so ALL investigation-derived
#      fields, including target, are `not_observable`. answer_strategy=CHAT
#      and llm_usage_reason=ROUTING_FALLBACK ARE explicitly set on this path
#      and are observable.
#
#   4. "runner_exception" — the exception escaped `run_with_steps()` itself
#      (this runner's own try/except in `run_baseline()`, not the agent's).
#      We know nothing: every field is `not_observable`.
#
# "investigated" (investigation is not None) is the normal, fully-observable
# case: every field is scored normally.

_INVESTIGATION_FIELDS = (
    "concepts",
    "operation",
    "intent",
    "target",
    "params",
    "answer_type",
    "required_evidence",
)

_FORCED_NOT_OBSERVABLE_BY_CONTEXT: dict[str, frozenset[str]] = {
    "target_shortcircuit": frozenset(_INVESTIGATION_FIELDS) - {"target"},
    "pipeline_shortcircuit": frozenset(_INVESTIGATION_FIELDS),
    "runner_exception": frozenset(_INVESTIGATION_FIELDS),
    # "chat" and "investigated" have no forced gaps (empty set via .get default).
}

# Fields where a missing/None *actual* value (not context-forced) means the
# trace never recorded a value, rather than the value legitimately being None.
_NONE_MEANS_NOT_OBSERVABLE_FIELDS = ("answer_strategy", "llm_usage_reason")


def investigation_context(investigation: Any, trace_dict: dict[str, Any]) -> str:
    """Classify *why* investigation is None (or that it isn't), so the scorer
    can tell a structural short-circuit apart from a real missing value.
    See the tri-state scoring comment block above for the full rationale.
    """
    failure_stage = trace_dict.get("failure_stage")
    if failure_stage == "runner_exception":
        return "runner_exception"
    if investigation is not None:
        return "investigated"
    if failure_stage == "target":
        return "target_shortcircuit"
    if failure_stage == "pipeline":
        return "pipeline_shortcircuit"
    return "chat"


def _field_status(
    field: str,
    expected_value: Any,
    actual_value: Any,
    context: str,
) -> str:
    """Return "match" | "mismatch" | "not_observable" for one field.

    Never treats a not_observable field as a mismatch (requirement: a field
    missing because of an investigation/trace short-circuit must not count
    against accuracy) and never fabricates a value to compare instead.
    """
    if field in _FORCED_NOT_OBSERVABLE_BY_CONTEXT.get(context, frozenset()):
        return "not_observable"
    if field in _NONE_MEANS_NOT_OBSERVABLE_FIELDS and actual_value is None:
        return "not_observable"

    if field in ("concepts", "required_evidence"):
        ok = sorted(expected_value or []) == sorted(actual_value or [])
    elif field == "params":
        ok = (expected_value or {}) == (actual_value or {})
    else:
        ok = expected_value == actual_value
    return "match" if ok else "mismatch"


def score_case(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Compare one golden case's expected and actual stage fields.

    `actual` must carry a `"_context"` key (set by `extract_actual`) so the
    scorer knows which fields are structurally not_observable for this case.
    Falls back to "investigated" (no forced gaps) if absent, e.g. for
    hand-built `actual` dicts in tests that don't go through extract_actual.
    """
    context = actual.get("_context", "investigated")
    field_status = {
        field: _field_status(field, expected.get(field), actual.get(field), context)
        for field in _ALL_SCORED_FIELDS
    }

    core_pass = all(field_status[field] == "match" for field in _CORE_FIELDS)

    return {
        "field_status": field_status,
        "core_pass": core_pass,
        "context": context,
        "expected": expected,
        "actual": actual,
    }


def _config_hash(project_root: Path) -> str:
    """Hash model and target configuration without exposing credentials."""
    digest = hashlib.sha256()
    found_any = False
    for name in ("targets.json", "servers.json"):
        path = project_root / name
        if path.is_file():
            digest.update(path.read_bytes())
            found_any = True
    return digest.hexdigest()[:16] if found_any else "unknown"


def _resolve_model_context(server_name: str | None) -> dict[str, Any]:
    """Resolve the effective model server without exposing its API key."""
    from src.shared.config import get_config

    config = get_config()
    if not config.servers:
        return {
            "configured": False,
            "server_name": "",
            "model": "",
            "provider": "",
        }

    resolved_name = server_name or config.active_server_name
    if not resolved_name:
        raise BaselinePreflightError(
            "servers.json contains model servers but active_server is empty; "
            "pass --server with a configured server name."
        )
    if resolved_name not in config.servers:
        available = ", ".join(sorted(config.servers)) or "(none)"
        raise BaselinePreflightError(
            f"Model server '{resolved_name}' is not configured. Available: {available}."
        )

    raw = config.servers[resolved_name]
    return {
        "configured": True,
        "server_name": resolved_name,
        "model": str(raw.get("model", "")),
        "provider": str(raw.get("provider", "")),
    }


def _runner_exception_result(exc: Exception) -> dict[str, Any]:
    """Build a synthetic result for an exception that escaped the agent
    itself (not one of the agent's own handled failure paths). We genuinely
    do not know what the pipeline would have produced, so `answer_strategy`
    and `llm_usage_reason` are left `None` rather than fabricated — the
    tri-state scorer turns "None" into `not_observable`, never a mismatch.
    """
    return {
        "response": "",
        "steps": [],
        "investigation": None,
        "trace_id": None,
        "execution_trace": {
            "failure_stage": "runner_exception",
            "failure_reason": str(exc)[:500],
            "answer_strategy": None,
            "llm_usage_reason": None,
            "total_duration_ms": None,
        },
    }


def run_baseline(
    golden_path: Path,
    server_name: str | None,
    target_store_path: str,
    *,
    smoke: bool = False,
    health_timeout: float = 5.0,
    agent_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run all cases through one agent instance and return a report.

    Normal mode requires a configured, reachable model.  Smoke mode injects
    ``UnconfiguredAssessmentAdapter`` deliberately and marks the report as
    non-meaningful, so setup mode can never masquerade as a 0% baseline.
    """
    if not golden_path.is_file():
        raise BaselinePreflightError(f"Golden dataset not found: {golden_path}")

    model_context = _resolve_model_context(server_name)

    if not smoke and not model_context["configured"]:
        raise BaselinePreflightError(
            "No model is configured in servers.json. A meaningful baseline was "
            "not run. Configure a model, or use --smoke for a non-baseline smoke run."
        )

    if agent_factory is None:
        from src.agent.runtime_factory import create_deterministic_agent

        agent_factory = create_deterministic_agent

    effective_server = model_context["server_name"] or None
    if smoke:
        from src.model.unconfigured_adapter import UnconfiguredAssessmentAdapter

        agent = agent_factory(
            target_store_path=target_store_path,
            server_name=None,
            assessment_adapter=UnconfiguredAssessmentAdapter(),
        )
        model_health_ok: bool | None = None
    else:
        agent = agent_factory(
            target_store_path=target_store_path,
            server_name=effective_server,
        )
        model_health_ok = bool(agent.health_check(timeout=health_timeout))
        if not model_health_ok:
            raise BaselinePreflightError(
                f"Configured model server '{effective_server}' failed its health "
                "check. No baseline report was written."
            )

    cases = load_golden_cases(golden_path)
    case_reports: list[dict[str, Any]] = []

    for case in cases:
        started = time.perf_counter()
        try:
            result = agent.run_with_steps(case["question"])
            error = None
        except Exception as exc:  # noqa: BLE001 - preserve the remaining run
            result = _runner_exception_result(exc)
            error = str(exc)[:500]
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

        actual = extract_actual(result)
        scored = score_case(case["expected"], actual)
        case_reports.append(
            {
                "id": case["id"],
                "group": case["group"],
                "question": case["question"],
                "tags": case.get("tags", []),
                "error": error,
                "elapsed_ms": elapsed_ms,
                **scored,
            }
        )

    run_context = {
        "run_mode": "smoke" if smoke else "baseline",
        "baseline_status": "smoke_only" if smoke else "completed",
        "meaningful_baseline": not smoke and bool(model_health_ok),
        "model_configured": bool(model_context["configured"]),
        "model_health_ok": model_health_ok,
        "resolved_server": effective_server or "",
        "resolved_model": model_context["model"],
        "resolved_provider": model_context["provider"],
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
    case_reports: list[dict[str, Any]],
    golden_path: Path,
    server_name: str | None,
    *,
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = len(case_reports)
    context = run_context or {
        "run_mode": "baseline",
        "baseline_status": "completed",
        "meaningful_baseline": True,
        "model_configured": True,
        "model_health_ok": True,
        "resolved_server": server_name or "",
        "resolved_model": "",
        "resolved_provider": "",
    }

    def _field_counts(field: str) -> dict[str, int]:
        counts = {"match": 0, "mismatch": 0, "not_observable": 0}
        for report in case_reports:
            counts[report["field_status"].get(field, "not_observable")] += 1
        return counts

    def _observable_accuracy(counts: dict[str, int]) -> float | None:
        observable = counts["match"] + counts["mismatch"]
        if observable == 0:
            return None
        return round(counts["match"] / observable, 4)

    stage_accuracy: dict[str, dict[str, Any]] = {}
    for field in _ALL_SCORED_FIELDS:
        counts = _field_counts(field)
        stage_accuracy[field] = {**counts, "observable_accuracy": _observable_accuracy(counts)}

    # strict_correct_investigation_rate: identical bar to the original
    # core_pass computation (ALL _CORE_FIELDS must be "match"). not_observable
    # does NOT count as a pass here — this rate is intentionally unchanged by
    # the tri-state refinement (see DR1-005 follow-up requirement #4).
    correct_count = sum(1 for report in case_reports if report["core_pass"])
    strict_correct_investigation_rate = round(correct_count / total, 4) if total else 0.0
    # Kept for backward compatibility with earlier report consumers/tests.
    observed_core_pass_rate = strict_correct_investigation_rate
    meaningful = bool(context["meaningful_baseline"])

    # observable_core_accuracy: of the _CORE_FIELDS instances we actually got
    # a value for (excluding not_observable), what fraction matched? This is
    # the fairer "were we right when we could see the field at all" measure.
    core_field_statuses = [
        report["field_status"][field] for report in case_reports for field in _CORE_FIELDS
    ]
    observable_core_statuses = [s for s in core_field_statuses if s != "not_observable"]
    observable_core_accuracy = (
        round(sum(1 for s in observable_core_statuses if s == "match") / len(observable_core_statuses), 4)
        if observable_core_statuses
        else None
    )

    # trace_completeness_rate: how much of the core trace is even usable for
    # scoring today — a diagnostic for instrumentation gaps (DR1-308/505/etc),
    # independent of whether the observable part was correct.
    trace_completeness_rate = (
        round(len(observable_core_statuses) / len(core_field_statuses), 4)
        if core_field_statuses
        else 0.0
    )

    def rate(predicate: Callable[[dict[str, Any]], bool]) -> float:
        if total == 0:
            return 0.0
        return round(sum(1 for report in case_reports if predicate(report)) / total, 4)

    deterministic_answer_coverage = rate(
        lambda report: report["actual"]["answer_strategy"]
        in ("DETERMINISTIC_FACT", "DETERMINISTIC_RESPONDER")
    )
    expected_assessment_rate = rate(
        lambda report: report["actual"]["llm_usage_reason"]
        == "EXPECTED_ASSESSMENT"
    )
    routing_fallback_rate = rate(
        lambda report: report["actual"]["llm_usage_reason"] == "ROUTING_FALLBACK"
    )
    insufficient_evidence_rate = rate(
        lambda report: report["actual"]["llm_usage_reason"]
        == "INSUFFICIENT_EVIDENCE"
    )

    by_group: dict[str, dict[str, Any]] = {}
    for report in case_reports:
        group = report["group"]
        by_group.setdefault(group, {"total": 0, "core_pass": 0})
        by_group[group]["total"] += 1
        if report["core_pass"]:
            by_group[group]["core_pass"] += 1
    for stats in by_group.values():
        stats["observed_core_pass_rate"] = round(
            stats["core_pass"] / stats["total"], 4
        )
        stats["strict_correct_investigation_rate"] = stats["observed_core_pass_rate"]
        stats["correct_investigation_rate"] = (
            stats["observed_core_pass_rate"] if meaningful else None
        )

    durations = sorted(
        report["actual"]["total_duration_ms"]
        for report in case_reports
        if report["actual"]["total_duration_ms"] is not None
    )
    median_ms = durations[len(durations) // 2] if durations else None
    p95_ms = durations[min(int(len(durations) * 0.95), len(durations) - 1)] if durations else None

    meta = collect_benchmark_metadata(server_name=server_name)
    if context.get("resolved_model"):
        meta["model"] = context["resolved_model"]
    if context.get("resolved_provider"):
        meta["provider"] = context["resolved_provider"]
    meta.update(context)
    meta["config_hash"] = _config_hash(PROJECT_ROOT)
    meta["golden_dataset_path"] = str(golden_path)
    meta["golden_dataset_cases_total"] = total
    meta["not_authoritative_fields"] = list(_APPROXIMATE_FIELDS)
    meta["not_authoritative_reason"] = None

    # Three separate diagnostic buckets, kept apart on purpose:
    #   - behavioral_mismatches: real disagreements between expected and
    #     actual, on fields we *could* observe. These are pipeline bugs.
    #   - trace_observability_gaps: fields we structurally could not observe
    #     for this case (short-circuit or missing trace value). These are
    #     instrumentation gaps (DR1-308/505/etc), not (necessarily) bugs.
    #   - approximate_fields: retained for backward-compatible report shape.
    behavioral_mismatches = [
        {
            "id": report["id"],
            "group": report["group"],
            "fields": [
                field
                for field in _CORE_FIELDS
                if report["field_status"][field] == "mismatch"
            ],
        }
        for report in case_reports
        if any(report["field_status"][field] == "mismatch" for field in _CORE_FIELDS)
    ]
    trace_observability_gaps = [
        {
            "id": report["id"],
            "group": report["group"],
            "context": report["context"],
            "fields": [
                field
                for field in _CORE_FIELDS
                if report["field_status"][field] == "not_observable"
            ],
        }
        for report in case_reports
        if any(
            report["field_status"][field] == "not_observable" for field in _CORE_FIELDS
        )
    ]

    return {
        "metadata": meta,
        "summary": {
            "cases_total": total,
            "correct_investigation_rate": (
                observed_core_pass_rate if meaningful else None
            ),
            "observed_core_pass_rate": observed_core_pass_rate,
            "strict_correct_investigation_rate": strict_correct_investigation_rate,
            "observable_core_accuracy": observable_core_accuracy,
            "trace_completeness_rate": trace_completeness_rate,
            "stage_accuracy": stage_accuracy,
            "deterministic_answer_coverage": deterministic_answer_coverage,
            "expected_assessment_rate": expected_assessment_rate,
            "routing_fallback_rate": routing_fallback_rate,
            "insufficient_evidence_rate": insufficient_evidence_rate,
            "by_group": by_group,
            "latency_ms": {"median": median_ms, "p95": p95_ms},
        },
        "diagnostics": {
            "behavioral_mismatches": behavioral_mismatches,
            "trace_observability_gaps": trace_observability_gaps,
            "approximate_fields": list(_APPROXIMATE_FIELDS),
        },
        "cases": case_reports,
    }


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["metadata"]
    summary = report["summary"]
    meaningful = bool(meta.get("meaningful_baseline"))

    lines = [
        "# Orion Baseline Report (DR1-005)",
        "",
        f"- Run mode: {meta.get('run_mode', 'unknown')}",
        f"- Baseline status: {meta.get('baseline_status', 'unknown')}",
        f"- Meaningful baseline: {str(meaningful).lower()}",
        f"- Commit: {meta.get('git_commit', 'unknown')}",
        f"- Config hash: {meta.get('config_hash', 'unknown')}",
        f"- Model/provider: {meta.get('model', 'unknown')} / "
        f"{meta.get('provider', 'unknown')}",
        f"- Captured at: {meta.get('captured_at', 'unknown')}",
        f"- Golden dataset: {meta.get('golden_dataset_path', 'unknown')} "
        f"({meta.get('golden_dataset_cases_total', 0)} scorable cases)",
        "",
        "> `routing_status` and `evidence_status` are first-class trace fields.",
        "",
    ]

    def _fmt_pct(value: float | None) -> str:
        return f"{value:.2%}" if value is not None else "n/a"

    if meaningful:
        lines += [
            "## Headline: correct_investigation_rate (strict) = "
            f"{summary['correct_investigation_rate']:.2%}",
            "",
        ]
    else:
        lines += [
            "## Smoke run — not a meaningful baseline",
            "",
            "`correct_investigation_rate` is intentionally not reported because "
            "the run did not use a configured, healthy assessment model.",
            "",
            f"- observed_core_pass_rate: {summary['observed_core_pass_rate']:.2%}",
            "",
        ]

    lines += [
        "## Metrics",
        "",
        "- `strict_correct_investigation_rate` — ALL core fields must be "
        "`match`; `not_observable` counts as failing, same bar as before "
        "this refinement, unchanged on purpose: "
        f"{_fmt_pct(summary['strict_correct_investigation_rate'])}",
        "- `observable_core_accuracy` — of core-field instances we could "
        "actually observe (excludes `not_observable`), fraction that "
        f"matched: {_fmt_pct(summary['observable_core_accuracy'])}",
        "- `trace_completeness_rate` — fraction of core-field instances that "
        "were observable at all (independent of correctness): "
        f"{_fmt_pct(summary['trace_completeness_rate'])}",
        "",
        "## Stage accuracy",
        "",
        "| Field | Match | Mismatch | Not observable | Observable accuracy |",
        "|---|---|---|---|---|",
    ]
    for field, counts in summary["stage_accuracy"].items():
        marker = " *(approx.)*" if field in _APPROXIMATE_FIELDS else ""
        lines.append(
            f"| {field}{marker} | {counts['match']} | {counts['mismatch']} | "
            f"{counts['not_observable']} | {_fmt_pct(counts['observable_accuracy'])} |"
        )

    lines += [
        "",
        "## Outcome rates",
        "",
        f"- deterministic_answer_coverage: "
        f"{summary['deterministic_answer_coverage']:.2%}",
        f"- expected_assessment_rate: {summary['expected_assessment_rate']:.2%}",
        f"- routing_fallback_rate: {summary['routing_fallback_rate']:.2%}",
        f"- insufficient_evidence_rate: "
        f"{summary['insufficient_evidence_rate']:.2%}",
        "",
        "## By group",
        "",
        "| Group | Cases | Rate |",
        "|---|---|---|",
    ]
    for group in sorted(summary["by_group"]):
        stats = summary["by_group"][group]
        rate_value = (
            stats["correct_investigation_rate"]
            if meaningful
            else stats["observed_core_pass_rate"]
        )
        label = "correct investigation" if meaningful else "observed core pass"
        lines.append(
            f"| {group} | {stats['total']} | {rate_value:.2%} ({label}) |"
        )

    lines += [
        "",
        "## Latency",
        "",
        f"- median total_duration_ms: {summary['latency_ms']['median']}",
        f"- p95 total_duration_ms: {summary['latency_ms']['p95']}",
        "",
        "## Behavioral mismatches",
        "",
        "Real disagreements on fields we could observe — these are pipeline "
        "bugs, not instrumentation gaps.",
        "",
    ]
    mismatches = report["diagnostics"]["behavioral_mismatches"]
    if not mismatches:
        lines.append("None.")
    else:
        for m in mismatches:
            lines.append(f"- `{m['id']}` ({m['group']}): {m['fields']}")

    lines += [
        "",
        "## Trace observability gaps",
        "",
        "Fields we structurally could not observe for this case (chat/target/"
        "pipeline short-circuit, or a trace value that was never set). Not "
        "counted as mismatches — see `docs/project/DETERMINISTIC_REASONING_"
        "BACKLOG.md` DR1-308/DR1-505 for closing these.",
        "",
    ]
    gaps = report["diagnostics"]["trace_observability_gaps"]
    if not gaps:
        lines.append("None.")
    else:
        for g in gaps:
            lines.append(f"- `{g['id']}` ({g['group']}, context={g['context']}): {g['fields']}")

    lines += [
        "",
        "## Approximate fields",
        "",
        (
            f"`{', '.join(report['diagnostics']['approximate_fields'])}`"
            if report["diagnostics"]["approximate_fields"]
            else "None; routing and evidence statuses are first-class trace fields."
        ),
        "",
    ]

    return "\n".join(lines) + "\n"


def _write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = "smoke" if report["metadata"]["run_mode"] == "smoke" else "baseline"
    json_path = output_dir / f"{suffix}_{stamp}.json"
    md_path = output_dir / f"{suffix}_{stamp}.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="DR1-005 baseline metrics runner.")
    parser.add_argument(
        "--golden",
        default=str(
            PROJECT_ROOT / "tests" / "data" / "qa_cases" / "golden_core.yaml"
        ),
    )
    parser.add_argument(
        "--output-dir", default=str(PROJECT_ROOT / "benchmark_results")
    )
    parser.add_argument("--server", default=None, help="Server name from servers.json.")
    parser.add_argument(
        "--target-store",
        default=str(PROJECT_ROOT / "targets.json"),
        help="Path to targets.json.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run without a model and write a clearly non-meaningful smoke report.",
    )
    parser.add_argument(
        "--health-timeout",
        type=float,
        default=5.0,
        help="Seconds allowed for the model preflight health check.",
    )
    args = parser.parse_args()

    try:
        report = run_baseline(
            Path(args.golden),
            args.server,
            args.target_store,
            smoke=args.smoke,
            health_timeout=args.health_timeout,
        )
    except (BaselinePreflightError, ValueError, OSError) as exc:
        print(f"Baseline not run: {exc}", file=sys.stderr)
        return 2

    json_path, md_path = _write_report(report, Path(args.output_dir))
    print(f"Report JSON: {json_path}")
    print(f"Report Markdown: {md_path}")
    print(
        "meaningful_baseline: "
        f"{str(report['metadata']['meaningful_baseline']).lower()}"
    )
    if report["metadata"]["meaningful_baseline"]:
        print(
            "correct_investigation_rate: "
            f"{report['summary']['correct_investigation_rate']:.2%}"
        )
    else:
        print(
            "Smoke run only; correct_investigation_rate was not published as a "
            "baseline."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
