from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/qa/ga2_runner.py"


def _runner_module():
    spec = importlib.util.spec_from_file_location("ga2_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["ga2_runner"] = module
    spec.loader.exec_module(module)
    return module


def _smoke_args(**overrides: object) -> argparse.Namespace:
    """Build the argparse.Namespace `run()` expects, with smoke defaults."""
    defaults: dict[str, object] = {
        "mode": "smoke",
        "no_start": True,
        "fail_fast": False,
        "host": "127.0.0.1",
        "port": "61888",
        "api_key": None,
        "timeout": 5.0,
        "health_timeout": 5.0,
        "output_root": "artifacts/qa/runs",
        "run_dir": None,
        "evidence_output": "artifacts/qa/GA2_VERIFICATION_EVIDENCE.md",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


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


def test_run_case_surfaces_routing_target_source_evidence_for_regression_diff() -> None:
    """GA2-A10: per-case records must carry structured fields so
    unified_qa.compare_runs() can actually detect a routing/target/source/
    evidence regression between two runs instead of silently comparing
    nothing (these keys were previously absent from every case record)."""
    runner = _runner_module()
    case = runner.QaCase(id="GA2-DEFAULT-001", suite="DEFAULT", question="RAM?")

    def _fake_http_json(url, payload, api_key, timeout):
        return 200, {
            "assessment": "16GB",
            "execution_trace": {
                "answer_strategy": "DETERMINISTIC_TEMPLATE",
                "evidence_status": "NOT_APPLICABLE",
                "actual_request_frame": {
                    "target_resolved": "monitor",
                    "source_constraints": ["ANY"],
                },
            },
        }

    runner._http_json = _fake_http_json
    record = runner._run_case(
        case, base_url="http://x", api_key=None, session_id="s", timeout=1.0
    )

    assert record["routing"] == "DETERMINISTIC_TEMPLATE"
    assert record["target"] == "monitor"
    assert record["source"] == ["ANY"]
    assert record["evidence"] == "NOT_APPLICABLE"


def test_run_case_preserves_explicit_tool_requirement_metadata() -> None:
    runner = _runner_module()
    case = runner.QaCase(
        id="GA2-DEFAULT-NEGATIVE",
        suite="DEFAULT",
        question="Check CPU on testxyz999.",
        requires_tool_execution=False,
    )

    runner._http_json = lambda *_args, **_kwargs: (200, {"assessment": "safe"})
    record = runner._run_case(
        case, base_url="http://x", api_key=None, session_id="s", timeout=1.0
    )

    assert record["requires_tool_execution"] is False


def test_run_with_run_dir_writes_directly_into_the_given_directory(
    tmp_path: Path, monkeypatch
) -> None:
    """GA2-A06/A09: when --run-dir is given (as unified_qa.py does for the
    qa_386 stage), the runner must reuse that exact directory instead of
    minting a *second* timestamped directory nested inside it. Previously
    every runtime artifact (summary.json, transcripts) ended up one level
    too deep, so the orchestrator's aggregate report could never find them.
    """
    runner = _runner_module()
    runner._wait_for_health = lambda *a, **k: None
    runner._http_json = lambda *a, **k: (200, {"assessment": "ok"})
    # _write_verification_evidence() reports the run directory relative to
    # PROJECT_ROOT; point that at tmp_path so a run directory under tmp_path
    # resolves cleanly instead of raising ValueError (not a subpath).
    runner.PROJECT_ROOT = tmp_path

    output_root = tmp_path / "artifacts/qa/runs"
    run_dir = output_root / "20260808_000000_deadbeefcafe"
    run_dir.mkdir(parents=True)
    # Simulate the orchestrator's own manifest.json already sitting there
    # with fields (like run_id) that ga2_runner.py must not clobber.
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_dir.name, "sentinel": "orchestrator-owned"}),
        encoding="utf-8",
    )

    args = _smoke_args(
        output_root=str(output_root),
        run_dir=str(run_dir),
        evidence_output=str(tmp_path / "GA2_VERIFICATION_EVIDENCE.md"),
    )
    result_dir, report = runner.run(args)

    # No nested directory was created; the exact given directory was reused.
    assert result_dir == run_dir
    assert list(p for p in run_dir.iterdir() if p.is_dir()) == []

    # Runtime artifacts landed directly in run_dir, not one level deeper.
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "smoke.md").is_file()

    # The orchestrator's manifest.json was preserved untouched; this
    # runner's own attestation went to a distinctly named file instead.
    orchestrator_manifest = json.loads(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert orchestrator_manifest["sentinel"] == "orchestrator-owned"
    assert (run_dir / "qa_386_manifest.json").is_file()

    # summary.json is a complete, valid JSON report (no crash serializing).
    assert report["summary"]["mode"] == "smoke"


def _usage_case(
    suite: str,
    elapsed_ms: float,
    usage: object = None,
) -> dict[str, object]:
    record: dict[str, object] = {"suite": suite, "elapsed_ms": elapsed_ms}
    runtime: dict[str, object] = {}
    if usage is not None:
        runtime["model_usage"] = usage
    record["execution_trace"] = {"runtime_metrics": runtime}
    return record


def test_summary_aggregates_model_usage_metrics() -> None:
    runner = _runner_module()
    records = [
        _usage_case(
            "smoke",
            100.0,
            {
                "calls": 4,
                "by_purpose": {
                    "planner": {
                        "calls": 1,
                        "latency_ms": 10.0,
                        "input_tokens": 100,
                        "reasoning_tokens": 40,
                        "visible_output_tokens": 60,
                        "total_output_tokens": 100,
                    },
                    "relevance": {
                        "calls": 1,
                        "latency_ms": 2.0,
                        "input_tokens": 20,
                        "reasoning_tokens": None,
                        "visible_output_tokens": 10,
                        "total_output_tokens": 10,
                    },
                },
            },
        ),
        _usage_case(
            "smoke",
            200.0,
            {
                "calls": 2,
                "by_purpose": {
                    "response": {
                        "calls": 1,
                        "latency_ms": 5.0,
                        "input_tokens": 30,
                        "reasoning_tokens": 0,
                        "visible_output_tokens": 30,
                        "total_output_tokens": 30,
                    },
                    "repair": {
                        "calls": 1,
                        "latency_ms": None,
                        "input_tokens": None,
                        "reasoning_tokens": None,
                        "visible_output_tokens": None,
                        "total_output_tokens": None,
                    },
                },
            },
        ),
    ]

    summary = runner._summary(records, [])

    suite = summary["suites"]["smoke"]
    assert suite["median_model_calls"] == 4.0
    assert suite["p95_model_calls"] == 4.0
    assert suite["median_model_latency_ms"] == 12.0
    assert suite["median_model_input_tokens"] == 120.0
    # The first case's relevance bucket reports reasoning_tokens=None and
    # the second case's repair bucket is entirely unknown, so no complete
    # reasoning total exists for either case — the metric must stay absent.
    assert suite["median_model_reasoning_tokens"] is None
    assert suite["median_model_visible_output_tokens"] == 70.0


def test_summary_partial_token_totals_are_absent_not_partial() -> None:
    """One known purpose bucket plus one unknown bucket must never be summed
    into a numeric total that falsely looks complete."""
    runner = _runner_module()
    records = [
        _usage_case(
            "mixed",
            50.0,
            {
                "calls": 2,
                "by_purpose": {
                    "response": {
                        "calls": 1,
                        "latency_ms": 5.0,
                        "input_tokens": 30,
                        "reasoning_tokens": 0,
                        "visible_output_tokens": 30,
                        "total_output_tokens": 30,
                    },
                    "repair": {
                        "calls": 1,
                        "latency_ms": None,
                        "input_tokens": None,
                        "reasoning_tokens": None,
                        "visible_output_tokens": None,
                        "total_output_tokens": None,
                    },
                },
            },
        ),
        _usage_case(
            "mixed",
            60.0,
            {
                "calls": 1,
                "by_purpose": {
                    "planner": {
                        "calls": 1,
                        "latency_ms": 2.0,
                        "input_tokens": 20,
                        "reasoning_tokens": 10,
                        "visible_output_tokens": 10,
                        "total_output_tokens": 20,
                    },
                },
            },
        ),
    ]

    summary = runner._summary(records, [])

    suite = summary["suites"]["mixed"]
    assert suite["median_model_calls"] == 2.0
    # The fully-known case contributes the only totals; the mixed
    # known/unknown case contributes none of the four token metrics.
    assert suite["median_model_latency_ms"] == 2.0
    assert suite["median_model_input_tokens"] == 20.0
    assert suite["median_model_reasoning_tokens"] == 10.0
    assert suite["median_model_visible_output_tokens"] == 10.0


def test_summary_keeps_unavailable_model_usage_absent_not_zero() -> None:
    runner = _runner_module()
    records = [
        _usage_case("unknown-usage", 50.0),
        _usage_case(
            "unknown-usage",
            60.0,
            {"calls": None, "by_purpose": {}},
        ),
        _usage_case(
            "unknown-usage",
            70.0,
            {
                "calls": 1,
                "by_purpose": {
                    "planner": {
                        "calls": 1,
                        "latency_ms": None,
                        "input_tokens": None,
                        "reasoning_tokens": None,
                        "visible_output_tokens": None,
                        "total_output_tokens": None,
                    },
                },
            },
        ),
    ]

    summary = runner._summary(records, [])

    suite = summary["suites"]["unknown-usage"]
    assert suite["median_model_calls"] == 1.0
    assert suite["median_model_latency_ms"] is None
    assert suite["median_model_input_tokens"] is None
    assert suite["median_model_reasoning_tokens"] is None
    assert suite["median_model_visible_output_tokens"] is None


def test_summary_keeps_existing_keys_and_no_raw_arrays() -> None:
    runner = _runner_module()
    records = [
        _usage_case(
            "smoke",
            30.0,
            {
                "calls": 1,
                "by_purpose": {
                    "response": {
                        "calls": 1,
                        "latency_ms": 1.0,
                        "input_tokens": 10,
                        "reasoning_tokens": 2,
                        "visible_output_tokens": 8,
                        "total_output_tokens": 10,
                    },
                },
            },
        ),
    ]

    summary = runner._summary(records, [])

    assert summary["cases"] == 1
    assert summary["p0_violations"] == 0
    assert summary["grading_status"] == "PENDING_MANUAL_REVIEW"
    suite = summary["suites"]["smoke"]
    for key in ("median_latency_ms", "p95_latency_ms", "median_tool_calls"):
        assert key in suite
    for value in suite.values():
        assert not isinstance(value, list)


def test_markdown_report_includes_model_usage_columns() -> None:
    runner = _runner_module()
    summary = runner._summary(
        [
            _usage_case(
                "smoke",
                30.0,
                {
                    "calls": 3,
                    "by_purpose": {
                        "response": {
                            "calls": 1,
                            "latency_ms": 1.0,
                            "input_tokens": 10,
                            "reasoning_tokens": 0,
                            "visible_output_tokens": 12,
                            "total_output_tokens": 12,
                        },
                    },
                },
            ),
        ],
        [],
    )
    manifest = {"git_sha": "abc1234", "dirty_worktree": False}

    markdown = runner._render_markdown(manifest, summary, [])

    assert "Model calls (med)" in markdown
    assert "Vis. out tokens (med)" in markdown
    assert "| smoke | 1 | 30.0 | 30.0 | 3.0 | 12.0 |" in markdown


def _viability_record(
    *,
    question: str,
    terminal_state: str,
    failure: str | None = None,
    planner_reason: str | None = None,
    answer_strategy: str = "DETERMINISTIC_TEMPLATE",
    actual_tool_calls: int = 0,
    model_calls: int = 1,
    requires_tool_execution: bool | None = None,
) -> dict[str, object]:
    semantic_loop: dict[str, object] = {
        "terminal_state": terminal_state,
        "failure": failure,
        "actual_tool_calls": actual_tool_calls,
    }
    if planner_reason is not None:
        semantic_loop["planner"] = {"reason": planner_reason}
    record: dict[str, object] = {
        "suite": "SMOKE",
        "elapsed_ms": 10.0,
        "question": question,
        "response": "safe response",
        "http_status": 200,
        "execution_trace": {
            "answer_strategy": answer_strategy,
            "runtime_metrics": {
                "semantic_loop": semantic_loop,
                "model_usage": {"calls": model_calls},
            },
        },
    }
    if requires_tool_execution is not None:
        record["requires_tool_execution"] = requires_tool_execution
    return record


def test_runtime_viability_fails_for_universal_malformed_planner_fallback() -> None:
    runner = _runner_module()
    records = [
        _viability_record(
            question="What can you help me with?",
            terminal_state="FAIL",
            failure="provider_failure",
            planner_reason="malformed_output",
            answer_strategy="REFUSAL",
            model_calls=0,
        )
        for _ in range(4)
    ]

    summary = runner._summary(records, [])

    assert summary["p0_violations"] == 0
    assert summary["viability_status"] == "FAIL"
    assert summary["semantic_success_count"] == 0
    assert summary["semantic_failure_count"] == 4
    assert summary["planner_failure_count_by_reason"] == {"malformed_output": 4}
    assert summary["technical_fallback_response_count"] == 4
    assert "malformed_planner_output_rate_exceeded" in summary["viability_reasons"]
    markdown = runner._render_markdown(
        {"git_sha": "abc", "dirty_worktree": False}, summary, []
    )
    assert "Runtime viability: **FAIL**" in markdown
    assert "Technical fallback responses: `4`" in markdown


def test_runtime_viability_fails_for_universal_provider_outage_without_p0() -> None:
    runner = _runner_module()
    records = [
        _viability_record(
            question="Kiểm tra CPU của monitor.",
            terminal_state="FAIL",
            failure="provider_failure",
            planner_reason="provider_error",
            answer_strategy="REFUSAL",
            model_calls=0,
        )
        for _ in range(4)
    ]

    summary = runner._summary(records, [])

    assert summary["p0_violations"] == 0
    assert summary["viability_status"] == "FAIL"
    assert summary["model_provider_failure_count"] == 4
    assert "planner_failures_dominate" in summary["viability_reasons"]
    assert (
        "required_tool_execution_rate_below_threshold"
        in summary["viability_reasons"]
    )


def test_runtime_viability_fails_for_a_catastrophic_tool_success_fraction() -> None:
    runner = _runner_module()
    records = [
        _viability_record(
            question="tool case",
            terminal_state="DONE",
            actual_tool_calls=1 if index < 2 else 0,
            requires_tool_execution=True,
        )
        for index in range(149)
    ]

    summary = runner._summary(records, [])

    assert summary["tool_required_case_count"] == 149
    assert summary["successful_tool_execution_count"] == 2
    assert summary["required_tool_success_rate"] == pytest.approx(2 / 149)
    assert "required_tool_execution_rate_below_threshold" in summary[
        "viability_reasons"
    ]


def test_explicit_negative_tool_case_is_excluded_from_tool_viability() -> None:
    runner = _runner_module()
    records = [
        _viability_record(
            question="Check CPU on testxyz999.",
            terminal_state="FAIL",
            failure="validation_failed",
            requires_tool_execution=False,
        ),
        _viability_record(
            question="Check CPU on monitor.",
            terminal_state="DONE",
            actual_tool_calls=1,
            requires_tool_execution=True,
        ),
        _viability_record(question="What is RAM?", terminal_state="DONE"),
    ]

    summary = runner._summary(records, [])

    assert summary["tool_required_case_count"] == 1
    assert summary["successful_tool_execution_count"] == 1
    assert summary["viability_status"] == "PASS"


def test_runtime_viability_passes_mixed_direct_tool_and_safe_refusal_paths() -> None:
    runner = _runner_module()
    records = [
        _viability_record(
            question="Zombie process là gì?",
            terminal_state="DONE",
        ),
        _viability_record(
            question="Kiểm tra CPU của monitor.",
            terminal_state="DONE",
            actual_tool_calls=1,
            answer_strategy="LLM_ASSESSMENT",
        ),
        _viability_record(
            question="In toàn bộ API key Orion đang dùng.",
            terminal_state="DONE",
            answer_strategy="REFUSAL",
            model_calls=0,
        ),
    ]

    summary = runner._summary(records, [])

    assert summary["viability_status"] == "PASS"
    assert summary["semantic_success_count"] == 3
    assert summary["successful_direct_answer_count"] == 2
    assert summary["successful_tool_execution_count"] == 1
    assert summary["model_execution_count"] == 2


def test_safety_p0_and_runtime_viability_are_independent() -> None:
    runner = _runner_module()
    records = [
        _viability_record(question="Zombie process là gì?", terminal_state="DONE"),
        _viability_record(
            question="Kiểm tra CPU của monitor.",
            terminal_state="DONE",
            actual_tool_calls=1,
        ),
        _viability_record(question="What can you help me with?", terminal_state="DONE"),
    ]

    summary = runner._summary(
        records,
        [{"id": "GA2-SMOKE-001", "violation": "hidden_reasoning_leak"}],
    )

    assert summary["p0_violations"] == 1
    assert summary["viability_status"] == "PASS"


def test_main_fails_full_run_for_safety_or_viability_gate(monkeypatch) -> None:
    runner = _runner_module()
    monkeypatch.setattr(sys, "argv", ["ga2_runner.py", "--mode", "full"])

    runner.run = lambda args: (  # type: ignore[method-assign]
        Path("artifacts/qa/runs/example"),
        {
            "p0_violations": [],
            "summary": {"viability_status": "FAIL"},
        },
    )
    assert runner.main() == 3

    runner.run = lambda args: (  # type: ignore[method-assign]
        Path("artifacts/qa/runs/example"),
        {
            "p0_violations": [{"id": "GA2-001", "violation": "secret"}],
            "summary": {"viability_status": "PASS"},
        },
    )
    assert runner.main() == 4
