from __future__ import annotations

from pathlib import Path

from scripts.qa.unified_qa import (
    RUNTIME_STAGES,
    TRANSCRIPTS,
    compare_runs,
    list_stages,
    new_run_dir,
    run_aggregate_report,
)


def test_full_qa_runtime_start_uses_the_qa_compose_overlay() -> None:
    """The canonical full run must provision the same QA-only targets as smoke."""
    start = next(stage for stage in RUNTIME_STAGES if stage.id == "docker_build_start")

    assert start.command == (
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.qa.yml",
        "up",
        "--build",
        "-d",
    )


def test_enumerate_all_stages_without_executing_them() -> None:
    """GA2-A06: runner can enumerate all stages without executing them."""
    stages = list_stages()
    assert stages == [
        "typecheck",
        "ruff",
        "pytest",
        "run_tests_v2",
        "run_baseline",
        "run_acceptance",
        "docker_build_start",
        "runtime_attestation",
        "qa_386",
        "aggregate_report",
        "regression_comparison",
    ]


def test_stage_outputs_preserved_under_one_run_id(tmp_path: Path) -> None:
    """GA2-A06: outputs are preserved under one run ID, never overwritten."""
    run_dir = new_run_dir(tmp_path, sha="abc123")
    assert run_dir.is_dir()
    assert "abc123" in run_dir.name

    # A second directory is distinct (no overwrite).
    run_dir_2 = new_run_dir(tmp_path, sha="abc123")
    assert run_dir_2 != run_dir
    assert run_dir_2.is_dir()


def test_aggregate_report_contains_full_ga2_a09_contract(tmp_path: Path) -> None:
    """GA2-A09: unified report must include the required fields."""
    manifest = {
        "run_id": "20260808_000000_abc123",
        "git_sha": "abc123",
        "dirty_worktree": False,
        "runner_version": "GA2.2",
        "api_image_id": "img",
        "api_container_id": "ctr",
        "feature_flags": {},
    }
    technical = [{"stage": "pytest", "status": "PASS", "exit_code": 0}]
    qa_report = {
        "summary": {
            "cases": 386,
            "p0_violations": 0,
            "suites": {"DEFAULT": {"cases": 193}},
        },
        "cases": [],
    }
    run_dir = new_run_dir(tmp_path, sha="abc123")
    for name in TRANSCRIPTS:
        (run_dir / name).write_text("# transcript", encoding="utf-8")

    report = run_aggregate_report(
        run_dir,
        manifest=manifest,
        technical=technical,
        qa_report=qa_report,
        comparison=None,
    )

    summary = report["summary"]
    assert summary["grading_status"] == "PENDING_MANUAL_REVIEW"
    assert report["manifest"]["git_sha"] == "abc123"
    assert report["manifest"]["run_id"] == "20260808_000000_abc123"
    assert report["technical_stages"][0]["status"] == "PASS"
    assert report["transcripts"] == {name: True for name in TRANSCRIPTS}
    assert "artifacts" in report


def test_aggregate_report_defaults_grading_to_pending_when_missing() -> None:
    """GA2-A09: missing grading never auto-promotes to accepted."""
    report = run_aggregate_report(
        Path("unused"),
        manifest={"run_id": "x", "git_sha": "y", "dirty_worktree": False},
        technical=[],
        qa_report=None,
        comparison=None,
    )
    assert report["summary"] == {"grading_status": "PENDING_MANUAL_REVIEW"}



def test_aggregate_report_preserves_safety_and_viability_gate_families(
    tmp_path: Path,
) -> None:
    viability_fields = {
        "p0_violations": 0,
        "viability_status": "FAIL",
        "viability_reasons": [
            "canonical_failures_dominate"
        ],
        "canonical_success_count": 0,
        "canonical_failure_count": 4,
        "runtime_failure_count_by_reason": {
            "model_failure": 4,
        },
        "model_failure_count": 4,
        "successful_tool_execution_count": 0,
        "successful_direct_answer_count": 0,
    }

    report = run_aggregate_report(
        tmp_path,
        manifest={
            "run_id": "x",
            "git_sha": "y",
            "dirty_worktree": False,
        },
        technical=[],
        qa_report={
            "summary": viability_fields,
            "cases": [],
        },
        comparison=None,
    )

    assert (
        report["summary"]["p0_violations"]
        == 0
    )
    assert (
        report["summary"]["viability_status"]
        == "FAIL"
    )
    assert report["summary"][
        "runtime_failure_count_by_reason"
    ] == {
        "model_failure": 4,
    }
    assert (
        report["qa"]["summary"][
            "model_failure_count"
        ]
        == 4
    )


def test_compare_runs_computes_counts_and_latency() -> None:
    """GA2-A10: comparison includes case count, P0 count and latency."""
    current = {
        "summary": {
            "cases": 386,
            "p0_violations": 0,
            "suites": {
                "DEFAULT": {
                    "cases": 193,
                    "median_latency_ms": 100.0,
                    "p95_latency_ms": 190.0,
                },
                "CORE": {
                    "cases": 66,
                    "median_latency_ms": 120.0,
                    "p95_latency_ms": 210.0,
                },
            },
        },
        "cases": [{"routing": "RESOLVED"}, {"routing": "GENERAL_CHAT"}],
    }
    previous = {
        "summary": {
            "cases": 386,
            "p0_violations": 1,
            "suites": {
                "DEFAULT": {
                    "cases": 193,
                    "median_latency_ms": 90.0,
                    "p95_latency_ms": 170.0,
                },
                "CORE": {
                    "cases": 66,
                    "median_latency_ms": 110.0,
                    "p95_latency_ms": 200.0,
                },
            },
        },
        "cases": [{"routing": "RESOLVED"}],
    }

    comparison = compare_runs(
        current,
        previous,
        previous_run="prev",
        current_run="curr",
    )
    assert comparison.previous_run == "prev"
    assert comparison.current_run == "curr"
    assert comparison.fields["case_count"] == {"previous": 386, "current": 386}
    assert comparison.fields["p0_violations"] == {"previous": 1, "current": 0}
    assert comparison.fields["latency_ms"]["current"]["median_latency_ms"] == 110.0
    assert comparison.fields["latency_ms"]["previous"]["median_latency_ms"] == 100.0
    assert comparison.fields["routing_regressions"]["current"] == {
        "GENERAL_CHAT": 1,
        "RESOLVED": 1,
    }
    assert comparison.fields["auto_promoted"] is False


def test_compare_runs_never_auto_promotes_ungraded_run() -> None:
    """GA2-A10: an ungraded run cannot be auto-promoted."""
    current = {"summary": {"cases": 386, "p0_violations": 0}, "cases": []}
    previous = {"summary": {"cases": 386, "p0_violations": 0}, "cases": []}
    comparison = compare_runs(current, previous, previous_run="p", current_run="c")
    payload = comparison.to_dict()
    assert payload["fields"]["auto_promoted"] is False


def test_compare_runs_handles_missing_summaries() -> None:
    comparison = compare_runs({}, {}, previous_run="p", current_run="c")
    assert "error" in comparison.fields
    assert comparison.fields["error"] == "missing summaries"
