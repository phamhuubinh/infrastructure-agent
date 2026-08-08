#!/usr/bin/env python3
"""GA2-A06/A09/A10 — Unified `qa-full` orchestrator.

This module implements the canonical `make qa-full` workflow as a single
deterministic orchestration while keeping the expensive 386-case runtime
benchmark out of the coding loop:

    typecheck
    → ruff
    → repository pytest
    → run_tests_v2
    → run_baseline
    → run_acceptance
    → one Docker build/start
    → runtime attestation
    → 386 Q&A
    → aggregate report
    → previous-run comparison

Design rules (from GA2_CONTINUATION_BACKLOG):

- `--plan` / `--list-stages` must enumerate all stages WITHOUT executing them,
  so unit tests never consume model/runtime quota.
- A nonzero technical-stage exit stops or marks the full run appropriately.
- Stage outputs are preserved under one run ID (never overwritten).
- Docker is built/started exactly once for the Q&A phase — never per suite.
- The final aggregate report carries the full GA2-A09 contract and always
  marks grading `PENDING_MANUAL_REVIEW` until the maintainer supplies grades.
- Comparison with a previous run (GA2-A10) never auto-promotes an ungraded run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RUNNER_VERSION = "GA2.2"

# Canonical artifact transcript names (GA2-A09).
TRANSCRIPTS = (
    "default_193.md",
    "cauhoi_kiemtra_v2.md",
    "cauhoi_phanb.md",
    "cauhoi_v4_adversarial.md",
    "cauhoi_v5_workflow.md",
)


@dataclass(frozen=True, slots=True)
class QaStage:
    """One ordered, deterministic stage in the `qa-full` workflow.

    ``runtime_only`` stages belong to the runtime Q&A phase and are skipped
    for ``--plan`` technical enumeration only in unit tests; both classes are
    always listed by ``list_stages``.
    """

    id: str
    description: str
    command: tuple[str, ...] = ()
    captures: tuple[Path, ...] = ()
    runtime_only: bool = False
    optional: bool = False


TECHNICAL_STAGES = (
    QaStage(
        "typecheck",
        "TypeScript + mypy type checking",
        ("make", "typecheck"),
    ),
    QaStage(
        "ruff",
        "Lint the repository",
        ("ruff", "check", "."),
    ),
    QaStage(
        "pytest",
        "Full repository pytest suite",
        (sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"),
    ),
    QaStage(
        "run_tests_v2",
        "Detailed integration test suite (in-process)",
        (sys.executable, "scripts/qa/run_tests_v2.py"),
    ),
    QaStage(
        "run_baseline",
        "Stage-level golden baseline metrics",
        (sys.executable, "scripts/qa/run_baseline.py", "--smoke"),
        optional=True,
    ),
    QaStage(
        "run_acceptance",
        "Offline acceptance gates over the baseline report",
        (
            sys.executable,
            "scripts/qa/run_acceptance.py",
            "--report",
            "__baseline_json__",
        ),
        optional=True,
    ),
)

RUNTIME_STAGES = (
    QaStage(
        "docker_build_start",
        "Build/start the intended Docker runtime once",
        ("docker", "compose", "up", "--build", "-d"),
        runtime_only=True,
    ),
    QaStage(
        "runtime_attestation",
        "Attest git SHA, image/container, flags",
        runtime_only=True,
    ),
    QaStage(
        "qa_386",
        "Canonical 386-case GA2 runtime Q&A",
        (sys.executable, "scripts/qa/ga2_runner.py", "--mode", "full", "--no-start"),
        runtime_only=True,
    ),
    QaStage(
        "aggregate_report",
        "Unified GA2 aggregate report",
        runtime_only=True,
    ),
    QaStage(
        "regression_comparison",
        "Compare with the selected previous run",
        runtime_only=True,
    ),
)

ALL_STAGES = TECHNICAL_STAGES + RUNTIME_STAGES


def enumerate_stages() -> tuple[QaStage, ...]:
    """Return the canonical ordered stage list (GA2-A06 enumeration)."""
    return ALL_STAGES


def list_stages() -> list[str]:
    """Return stage ids only, used by ``--list-stages`` and unit tests."""
    return [stage.id for stage in ALL_STAGES]


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _dirty_worktree() -> bool:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(completed.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return True  # Unknown cleanliness fails safe.


def _command_output(command: tuple[str, ...]) -> str | None:
    try:
        completed = subprocess.run(
            list(command),
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def feature_flags() -> dict[str, str]:
    """Collect safe flag names only; never credentials or endpoints."""
    allowed = (
        "ORION_FEATURE",
        "ORION_GENERAL_AGENT",
        "ORION_EXTERNAL_VERIFICATION",
        "ORION_SOURCE_CONSTRAINTS",
        "ORION_CLAIM_GUARD",
        "ORION_DETERMINISTIC",
        "ORION_ENV",
    )
    values: dict[str, str] = {}
    for key, value in os.environ.items():
        if any(key.startswith(prefix) for prefix in allowed):
            values[key] = value
    env_path = PROJECT_ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and any(key.strip().startswith(prefix) for prefix in allowed):
                values.setdefault(key.strip(), value.strip())
    return dict(sorted(values.items()))


def runtime_attestation() -> dict[str, object]:
    """GA2-A02/A09 runtime attestation: source + Docker identity + flags."""
    return {
        "run_id": None,  # Filled by the orchestrator run().
        "git_sha": _git_sha(),
        "dirty_worktree": _dirty_worktree(),
        "runner_version": RUNNER_VERSION,
        "api_image_id": _command_output(("docker", "compose", "images", "-q", "api")),
        "api_container_id": _command_output(("docker", "compose", "ps", "-q", "api")),
        "feature_flags": feature_flags(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# GA2-A10 — Regression comparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunComparison:
    """Deterministic comparison of two completed QA runs."""

    previous_run: str
    current_run: str
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_run": self.previous_run,
            "current_run": self.current_run,
            "fields": self.fields,
        }


def _summary_latency(summary: dict[str, object]) -> dict[str, object]:
    suites = summary.get("suites")
    if not isinstance(suites, dict):
        return {}
    medians: list[float] = []
    p95s: list[float] = []
    for values in suites.values():
        if not isinstance(values, dict):
            continue
        median = values.get("median_latency_ms")
        p95 = values.get("p95_latency_ms")
        if isinstance(median, (int, float)):
            medians.append(float(median))
        if isinstance(p95, (int, float)):
            p95s.append(float(p95))
    if not medians:
        return {}
    medians.sort()
    p95s.sort()
    midpoint = len(medians) // 2
    global_median = (
        medians[midpoint]
        if len(medians) % 2
        else (medians[midpoint - 1] + medians[midpoint]) / 2
    )
    return {
        "median_latency_ms": round(float(global_median), 3),
        "p95_latency_ms": p95s[min(len(p95s) - 1, int(len(p95s) * 0.95))],
    }


def compare_runs(
    current: dict[str, object],
    previous: dict[str, object],
    *,
    previous_run: str,
    current_run: str,
) -> RunComparison:
    """Compare two completed run summaries (GA2-A10).

    Compares case count, P0 count, FAIL/PARTIAL count, and median/p95 latency
    when structured data exists.  Never auto-promotes an ungraded run.
    """
    current_summary = current.get("summary")
    previous_summary = previous.get("summary")
    if not isinstance(current_summary, dict) or not isinstance(previous_summary, dict):
        return RunComparison(previous_run, current_run, {"error": "missing summaries"})
    if "suites" not in current_summary and "cases" not in current_summary:
        return RunComparison(previous_run, current_run, {"error": "missing summaries"})

    def _count(value: object) -> int:
        return int(value) if isinstance(value, (int, float)) else 0

    fields: dict[str, Any] = {
        "case_count": {
            "previous": _count(previous_summary.get("cases")),
            "current": _count(current_summary.get("cases")),
        },
        "p0_violations": {
            "previous": _count(previous_summary.get("p0_violations")),
            "current": _count(current_summary.get("p0_violations")),
        },
    }
    current_suites = current_summary.get("suites")
    previous_suites = previous_summary.get("suites")
    if isinstance(current_suites, dict) and isinstance(previous_suites, dict):
        current_counts = [
            int(v["cases"])
            for v in current_suites.values()
            if isinstance(v, dict) and isinstance(v.get("cases"), (int, float))
        ]
        previous_counts = [
            int(v["cases"])
            for v in previous_suites.values()
            if isinstance(v, dict) and isinstance(v.get("cases"), (int, float))
        ]
        fields["suite_case_counts"] = {
            "previous": sum(previous_counts),
            "current": sum(current_counts),
        }

    previous_latency = _summary_latency(previous_summary)
    current_latency = _summary_latency(current_summary)
    if previous_latency and current_latency:
        fields["latency_ms"] = {
            "previous": previous_latency,
            "current": current_latency,
        }

    # Structured route/target/source regressions when traces exist (additive).
    for key in ("routing", "target", "source", "evidence"):
        previous_rows = _structured_counts(previous.get("cases"), key)
        current_rows = _structured_counts(current.get("cases"), key)
        if previous_rows or current_rows:
            fields[f"{key}_regressions"] = {
                "previous": previous_rows,
                "current": current_rows,
            }

    fields["auto_promoted"] = False  # Never auto-promote an ungraded run.
    return RunComparison(previous_run, current_run, fields)


def _structured_counts(cases: object, key: str) -> dict[str, int]:
    """Count structured route/target/source/evidence values across a run."""
    if not isinstance(cases, list):
        return {}
    counts: dict[str, int] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        value = case.get(key)
        if value is None:
            continue
        label = str(value)
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# GA2-A06 — Orchestration
# ---------------------------------------------------------------------------


def new_run_dir(output_root: Path, *, sha: str | None = None) -> Path:
    """Create a fresh timestamp/git-SHA run directory (never overwritten).

    Uses microsecond precision so two calls within the same second cannot
    collide; a ``FileExistsError`` remains a loud signal rather than an
    accidental overwrite.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    run_dir = output_root / f"{stamp}_{(sha or 'unknown')[:12]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _run_subprocess(
    command: tuple[str, ...],
    *,
    run_dir: Path,
    stage_id: str,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run one stage, capture stdout/stderr under the run directory."""
    stdout_path = run_dir / f"{stage_id}.out.log"
    stderr_path = run_dir / f"{stage_id}.err.log"
    started = time.perf_counter()
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    try:
        with open(stdout_path, "w", encoding="utf-8") as stdout_fh:
            with open(stderr_path, "w", encoding="utf-8") as stderr_fh:
                completed = subprocess.run(
                    list(command),
                    cwd=PROJECT_ROOT,
                    env=merged_env,
                    check=False,
                    stdout=stdout_fh,
                    stderr=stderr_fh,
                )
        returncode = completed.returncode
    except (OSError, ValueError) as exc:
        returncode = -1
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(f"{exc}\n", encoding="utf-8")
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "stage": stage_id,
        "exit_code": returncode,
        "elapsed_ms": elapsed_ms,
        "stdout": stdout_path,
        "stderr": stderr_path,
        "status": "PASS" if returncode == 0 else "FAIL",
    }


def run_technical_stages(
    run_dir: Path,
    *,
    include_optional: bool = True,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, object]]:
    """Execute the ordered technical stages, capturing outputs per stage.

    A nonzero stage exit marks the stage FAIL and stops the chain (GA2-A06):
    an optional stage (e.g. ``run_baseline --smoke``) is recorded but does not
    abort the full run when it cannot produce a report.
    """
    results: list[dict[str, object]] = []
    for stage in TECHNICAL_STAGES:
        if stage.optional and not include_optional:
            results.append({**asdict(stage), "status": "SKIPPED"})
            continue
        if progress:
            progress(stage.id)
        command = _resolve_stage_command(stage, run_dir)
        result = _run_subprocess(command, run_dir=run_dir, stage_id=stage.id)
        results.append(result)
        if result["status"] == "FAIL" and not stage.optional:
            break
    return results


def _resolve_stage_command(stage: QaStage, run_dir: Path) -> tuple[str, ...]:
    """Resolve placeholder commands (e.g. the baseline JSON path)."""
    if stage.id != "run_acceptance":
        return stage.command
    baseline_json = next(run_dir.glob("baseline_*.json"), None)
    if baseline_json is None:
        # No baseline report was produced (smoke/non-meaningful); acceptance
        # stage cannot run — return a command that fails loudly with a clear
        # reason rather than silently skipping the gate.
        return (
            sys.executable,
            "-c",
            "import sys; print('No baseline JSON found; acceptance gates cannot "
            "run. Ensure run_baseline produced a report.', file=sys.stderr); "
            "sys.exit(2)",
        )
    return tuple(
        str(value) if value == "__baseline_json__" else value for value in stage.command
    )


class AggregateReport(TypedDict):
    """GA2-A09 unified aggregate report contract.

    ``qa`` and ``regression`` are ``None`` when the runtime Q&A phase or a
    previous-run comparison did not run (e.g. technical-only or failed runs).
    """

    manifest: dict[str, object]
    technical_stages: list[dict[str, object]]
    qa: dict[str, object] | None
    summary: dict[str, object]
    regression: dict[str, object] | None
    transcripts: dict[str, bool]
    artifacts: list[str]


def run_aggregate_report(
    run_dir: Path,
    *,
    manifest: dict[str, object],
    technical: list[dict[str, object]],
    qa_report: dict[str, object] | None,
    comparison: RunComparison | None,
) -> AggregateReport:
    """Build the unified GA2 aggregate report (GA2-A09).

    The report never claims acceptance from transport success alone; grading
    remains ``PENDING_MANUAL_REVIEW`` until the maintainer supplies grades.
    """
    raw_summary = qa_report.get("summary") if qa_report else None
    summary: dict[str, Any] = dict(raw_summary) if isinstance(raw_summary, dict) else {}
    summary.setdefault("grading_status", "PENDING_MANUAL_REVIEW")
    artifacts: list[str] = []
    transcripts: dict[str, bool] = {name: False for name in TRANSCRIPTS}
    if run_dir.is_dir():
        transcripts = {name: (run_dir / name).exists() for name in TRANSCRIPTS}
        artifacts = sorted(str(path.name) for path in run_dir.iterdir())
    report: AggregateReport = {
        "manifest": manifest,
        "technical_stages": technical,
        "qa": qa_report,
        "summary": summary,
        "regression": comparison.to_dict() if comparison else None,
        "transcripts": transcripts,
        "artifacts": artifacts,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the canonical unified `make qa-full` orchestration."
    )
    parser.add_argument(
        "--list-stages",
        action="store_true",
        help="Print the ordered stage ids without executing anything.",
    )
    parser.add_argument(
        "--technical-only",
        action="store_true",
        help="Run only the technical stages; do not start Docker or the 386 Q&A.",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/qa/runs",
        help="Root directory for run artifacts (timestamp_sha subdirectories).",
    )
    parser.add_argument(
        "--previous-run",
        default=None,
        help="Optional previous run directory for GA2-A10 regression comparison.",
    )
    args = parser.parse_args()

    if args.list_stages:
        for stage_id in list_stages():
            print(stage_id)
        return 0

    sha = _git_sha()
    run_dir = new_run_dir(Path(args.output_root), sha=sha)

    manifest = runtime_attestation()
    manifest["run_id"] = run_dir.name
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    technical = run_technical_stages(run_dir)
    for result in technical:
        status = result["status"]
        exit_code = result["exit_code"]
        print(f"[{result['stage']}] {status} (exit={exit_code})")

    failed_technical = any(
        result["status"] == "FAIL"
        for result in technical
        if result["stage"] not in {"run_baseline", "run_acceptance"}
    )
    if failed_technical:
        print(
            "A required technical stage failed; the full run is stopped.",
            file=sys.stderr,
        )
        report = run_aggregate_report(
            run_dir,
            manifest=manifest,
            technical=technical,
            qa_report=None,
            comparison=None,
        )
        (run_dir / "summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return 1

    if args.technical_only:
        report = run_aggregate_report(
            run_dir,
            manifest=manifest,
            technical=technical,
            qa_report=None,
            comparison=None,
        )
        (run_dir / "summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Technical stages complete (no runtime Q&A): {run_dir}")
        return 0

    # ------------------------------------------------------------------
    # Runtime phase: one Docker build/start, attestation, then the 386 Q&A.
    # ------------------------------------------------------------------
    docker_result = _run_subprocess(
        ("docker", "compose", "up", "--build", "-d"),
        run_dir=run_dir,
        stage_id="docker_build_start",
    )
    if docker_result["status"] == "FAIL":
        print("Docker build/start failed; stopping.", file=sys.stderr)
        return 1

    _run_subprocess(
        (
            sys.executable,
            "scripts/qa/ga2_runner.py",
            "--mode",
            "full",
            "--no-start",
            "--output-root",
            str(run_dir),
        ),
        run_dir=run_dir,
        stage_id="qa_386",
    )

    qa_report: dict[str, object] | None = None
    summary_json = run_dir / "summary.json"
    # ga2_runner writes its own summary.json inside the same run directory.
    # Prefer the runner's own file when present.
    if summary_json.is_file():
        try:
            qa_report = json.loads(summary_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            qa_report = None

    comparison: RunComparison | None = None
    if args.previous_run:
        previous_dir = Path(args.previous_run)
        if not previous_dir.is_absolute():
            previous_dir = Path(args.output_root) / previous_dir
        previous_summary = previous_dir / "summary.json"
        if previous_summary.is_file() and qa_report is not None:
            try:
                previous_payload = json.loads(
                    previous_summary.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                previous_payload = {}
            comparison = compare_runs(
                qa_report,
                previous_payload,
                previous_run=previous_dir.name,
                current_run=run_dir.name,
            )

    report = run_aggregate_report(
        run_dir,
        manifest=manifest,
        technical=technical,
        qa_report=qa_report,
        comparison=comparison,
    )
    (run_dir / "aggregate_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Unified QA report: {run_dir / 'aggregate_report.json'}")
    report_summary = report.get("summary")
    grading_status = (
        report_summary.get("grading_status", "PENDING_MANUAL_REVIEW")
        if isinstance(report_summary, dict)
        else "PENDING_MANUAL_REVIEW"
    )
    print(f"Grading status: {grading_status}")
    return 0 if not failed_technical else 1


if __name__ == "__main__":
    raise SystemExit(main())
