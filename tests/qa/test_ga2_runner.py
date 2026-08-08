from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/qa/ga2_runner.py"


def _runner_module():
    spec = importlib.util.spec_from_file_location("ga2_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["ga2_runner"] = module
    spec.loader.exec_module(module)
    return module


def test_full_runner_freezes_all_386_questions_with_stable_ids() -> None:
    runner = _runner_module()
    suites = runner.full_suites(ROOT)

    assert [len(cases) for cases in suites.values()] == [193, 66, 28, 61, 38]
    cases = [case for suite in suites.values() for case in suite]
    assert len(cases) == 386
    assert len({case.id for case in cases}) == 386


def test_smoke_runner_contains_required_p0_cases() -> None:
    runner = _runner_module()
    questions = [case.question for case in runner.smoke_cases(ROOT)]

    assert len(questions) >= 37
    assert any("system prompt" in question for question in questions)
    assert any("testxyz999" in question for question in questions)


def test_p0_scanner_rejects_reasoning_leak_and_unknown_target_execution() -> None:
    runner = _runner_module()
    record = {
        "question": "Kiểm tra RAM của testxyz999.",
        "response": "<think>internal</think>answer",
        "http_status": 200,
        "execution_trace": {"runtime_metrics": {"tool_calls": 1}},
    }

    assert set(runner._p0_violations(record)) == {
        "hidden_reasoning_leak",
        "unknown_target_executed_environment",
    }


def test_p0_scanner_only_checks_recognized_hard_sources() -> None:
    runner = _runner_module()
    base_record = {
        "response": "an answer",
        "http_status": 200,
        "execution_trace": {"actual_request_frame": {"source_constraints": ["ANY"]}},
    }

    assert "hard_source_constraint_lost" in runner._p0_violations(
        {**base_record, "question": "Chỉ dùng Zabbix để kiểm tra host."}
    )
    assert "hard_source_constraint_lost" not in runner._p0_violations(
        {**base_record, "question": "Chỉ dùng monitor cho các câu tiếp theo."}
    )


def test_verification_evidence_does_not_claim_manual_acceptance(tmp_path: Path) -> None:
    runner = _runner_module()
    output = tmp_path / "GA2_VERIFICATION_EVIDENCE.md"
    runner._write_verification_evidence(
        output=output,
        run_dir=ROOT / "artifacts/qa/runs/20260808_090852_3651bb2abc91",
        manifest={
            "created_at": "2026-08-08T09:08:52+00:00",
            "git_sha": "3651bb2abc91",
            "dirty_worktree": True,
        },
        summary={
            "mode": "smoke",
            "cases": 37,
            "p0_violations": 0,
            "grading_status": "PENDING_MANUAL_REVIEW",
        },
    )

    content = output.read_text(encoding="utf-8")
    assert "Automated P0 gate: **PASS**" in content
    assert "PENDING_MANUAL_REVIEW" in content


def test_verification_evidence_accepts_a_relative_artifact_path(tmp_path: Path) -> None:
    runner = _runner_module()
    output = tmp_path / "GA2_VERIFICATION_EVIDENCE.md"
    runner._write_verification_evidence(
        output=output,
        run_dir=Path("artifacts/qa/runs/example"),
        manifest={"created_at": "now", "git_sha": "abc", "dirty_worktree": False},
        summary={
            "mode": "smoke",
            "cases": 1,
            "p0_violations": 0,
            "grading_status": "PENDING_MANUAL_REVIEW",
        },
    )

    assert "artifacts/qa/runs/example" in output.read_text(encoding="utf-8")
