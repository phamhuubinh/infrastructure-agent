from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def quality_verdicts():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "scripts" / "qa" / "quality_verdicts.py"
    specification = importlib.util.spec_from_file_location("orion_qa_quality_verdicts", path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def quality_fixture(quality_verdicts, tmp_path):  # type: ignore[no-untyped-def]
    report = tmp_path / "quality-report"
    report.mkdir()
    manifest = {
        "mode": "full",
        "execution_provenance": {"fingerprint": "execution-fingerprint"},
    }
    result = {
        "phase": "canonical",
        "id": "synthetic-synthesis",
        "category": "workflow",
        "manual_quality": True,
        "status": "MANUAL_REVIEW",
        "stability_diagnostic": {
            "events_truncated": False,
            "events": [
                {
                    "kind": "tool_result",
                    "data": {"state": "inactive"},
                    "data_truncated": False,
                },
                {
                    "kind": "assistant_message",
                    "content": "The service is inactive.",
                    "content_truncated": False,
                    "hidden_reasoning_omitted": False,
                    "terminal_response": True,
                },
            ],
        },
    }
    (report / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (report / "cases.jsonl").write_text(json.dumps(result) + "\n", encoding="utf-8")
    return report, manifest, result, quality_verdicts.review_subject(report, manifest, result)


def verdict(subject, decision="accepted"):  # type: ignore[no-untyped-def]
    return {
        "schema_version": 1,
        "run_id": subject["run_id"],
        "manifest_sha256": subject["manifest_sha256"],
        "execution_fingerprint": subject["execution_fingerprint"],
        "phase": subject["phase"],
        "case_id": subject["case_id"],
        "answer_sha256": subject["answer_sha256"],
        "evidence_sha256": subject["evidence_sha256"],
        "verdict": decision,
        "rationale": "Synthetic review rationale.",
        "reviewer": "offline-reviewer",
        "reviewed_at": "2026-09-06T00:00:00Z",
    }


def test_quality_overlay_keeps_execution_separate_and_requires_valid_review(
    quality_verdicts, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    report, manifest, result, subject = quality_fixture(quality_verdicts, tmp_path)

    pending = quality_verdicts.aggregate_quality(report, manifest, [result])
    assert pending["execution"] == {"MANUAL_REVIEW": 1}
    assert pending["quality"] == {"pending_review": 1}
    assert pending["cases"][0]["execution_status"] == "MANUAL_REVIEW"
    assert not quality_verdicts.quality_gate(pending, skip_policy="forbid")["passed"]

    accepted = quality_verdicts.aggregate_quality(report, manifest, [result], [verdict(subject)])
    assert accepted["quality"] == {"accepted": 1}
    assert quality_verdicts.quality_gate(accepted, skip_policy="forbid")["passed"]


def test_quality_overlay_rejects_stale_and_duplicate_sidecars(quality_verdicts, tmp_path) -> None:  # type: ignore[no-untyped-def]
    report, manifest, result, subject = quality_fixture(quality_verdicts, tmp_path)
    stale = verdict(subject)
    stale["answer_sha256"] = "0" * 64
    stale_aggregate = quality_verdicts.aggregate_quality(report, manifest, [result], [stale])
    stale_case = stale_aggregate["cases"][0]
    assert stale_case["quality_status"] == "pending_review"
    assert "does not match this artifact" in stale_case["quality_reason"]
    assert not quality_verdicts.quality_gate(stale_aggregate, skip_policy="forbid")["passed"]

    review = verdict(subject)
    duplicate = quality_verdicts.aggregate_quality(report, manifest, [result], [review, review])
    assert duplicate["cases"][0]["quality_status"] == "pending_review"
    assert "duplicate" in duplicate["cases"][0]["quality_reason"]
    assert not quality_verdicts.quality_gate(duplicate, skip_policy="forbid")["passed"]


@pytest.mark.parametrize("status", ["FAIL", "SKIP", "PASS", "incomplete"])
@pytest.mark.parametrize("sidecar_count", [0, 1, 2])
@pytest.mark.parametrize("next_turn_started", [False, True])
def test_nonterminal_execution_cannot_review_a_previous_turn(
    quality_verdicts, tmp_path, status, sidecar_count, next_turn_started
) -> None:  # type: ignore[no-untyped-def]
    report, manifest, result, previous_subject = quality_fixture(quality_verdicts, tmp_path)
    result["status"] = status
    if next_turn_started:
        result["stability_diagnostic"]["events"].append(
            {
                "kind": "tool_call",
                "tool_name": "synthetic.read",
                "arguments": {},
            }
        )
    subject = quality_verdicts.review_subject(report, manifest, result)
    assert subject["reviewable"] is False
    assert "execution did not reach reviewable terminal outcome" in subject["reason"]
    assert "answer_sha256" not in subject
    attempted = verdict(previous_subject)
    attempted["evidence_sha256"] = quality_verdicts._sha256(result["stability_diagnostic"])
    aggregate = quality_verdicts.aggregate_quality(
        report, manifest, [result], [attempted] * sidecar_count
    )
    assert aggregate["quality"] == {"not_assessable": 1}
    assert not quality_verdicts.quality_gate(aggregate, skip_policy="forbid")["passed"]
    assert quality_verdicts.validate_verdict(attempted, subject) is not None


@pytest.mark.parametrize("phase", ["canonical", "stability"])
def test_successful_multiturn_review_binds_final_answer(quality_verdicts, tmp_path, phase) -> None:  # type: ignore[no-untyped-def]
    report, manifest, result, previous_subject = quality_fixture(quality_verdicts, tmp_path)
    result["phase"] = phase
    result["stability_diagnostic"]["events"].append(
        {
            "kind": "assistant_message",
            "content": "Final turn two answer.",
            "terminal_response": True,
            "content_truncated": False,
        }
    )
    subject = quality_verdicts.review_subject(report, manifest, result)
    assert subject["reviewable"] is True
    assert subject["answer_sha256"] == hashlib.sha256(b"Final turn two answer.").hexdigest()
    assert subject["answer_sha256"] != previous_subject["answer_sha256"]
    assert subject["evidence_sha256"] == quality_verdicts._sha256(result["stability_diagnostic"])
    pending = quality_verdicts.aggregate_quality(report, manifest, [result])
    assert pending["quality"] == {"pending_review": 1}
    assert not quality_verdicts.quality_gate(pending, skip_policy="forbid")["passed"]
    accepted = quality_verdicts.aggregate_quality(report, manifest, [result], [verdict(subject)])
    assert accepted["quality"] == {"accepted": 1}
    assert quality_verdicts.quality_gate(accepted, skip_policy="forbid")["passed"]


@pytest.mark.parametrize("damage", ["missing", "terminal", "text", "events", "data"])
def test_quality_overlay_never_accepts_missing_or_truncated_terminal_evidence(
    quality_verdicts, tmp_path, damage
) -> None:  # type: ignore[no-untyped-def]
    report, manifest, result, subject = quality_fixture(quality_verdicts, tmp_path)
    diagnostic = result["stability_diagnostic"]
    if damage == "missing":
        del result["stability_diagnostic"]
    elif damage == "terminal":
        diagnostic["events"][-1]["terminal_response"] = False
    elif damage == "text":
        diagnostic["events"][-1]["content_truncated"] = True
    elif damage == "events":
        diagnostic["events_truncated"] = True
    else:
        diagnostic["events"][0]["data_truncated"] = True

    aggregate = quality_verdicts.aggregate_quality(report, manifest, [result])

    assert aggregate["quality"] == {"not_assessable": 1}
    assert not quality_verdicts.quality_gate(aggregate, skip_policy="forbid")["passed"]
    attempted = quality_verdicts.aggregate_quality(report, manifest, [result], [verdict(subject)])
    assert attempted["quality"] == {"not_assessable": 1}


def test_canonical_manual_capture_is_reviewable_and_exact_bound_offline(
    quality_verdicts, tmp_path, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "scripts" / "qa" / "runner.py"
    specification = importlib.util.spec_from_file_location("orion_qa_runner_quality", path)
    assert specification and specification.loader
    runner = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = runner
    specification.loader.exec_module(runner)
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: pytest.fail("process"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("network"))
    report, manifest, result, _ = quality_fixture(quality_verdicts, tmp_path)
    del result["stability_diagnostic"]
    answer = "Evidence-backed synthetic answer. " * 30
    result["manual_review_answer"] = answer[:512]
    timeline = [
        {
            "kind": "tool_result",
            "tool_name": "synthetic.read",
            "payload": {"result": {"data": {"state": "inactive", "password": "secret"}}},
        },
        {"kind": "assistant_message", "payload": {"content": answer, "metrics": {}}},
    ]
    runner._attach_stability_diagnostics(result, "canonical", [timeline], ("secret",))
    diagnostic = result["stability_diagnostic"]
    assert diagnostic["events"][-1]["content"] == answer
    assert diagnostic["events"][-1]["terminal_response"] is True
    assert "secret" not in json.dumps(diagnostic)
    (report / "cases.jsonl").write_text(json.dumps(result) + "\n", encoding="utf-8")
    before = {name: (report / name).read_bytes() for name in ("manifest.json", "cases.jsonl")}

    assert quality_verdicts.main(["inspect", str(report)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["quality"] == {"pending_review": 1}
    subject = inspected["cases"][0]["review_subject"]

    def digest(value):  # type: ignore[no-untyped-def]
        text = (
            value
            if isinstance(value, str)
            else json.dumps(value, sort_keys=True, separators=(",", ":"))
        )
        return hashlib.sha256(text.encode()).hexdigest()

    assert subject == {
        "run_id": report.name,
        "manifest_sha256": digest(manifest),
        "execution_fingerprint": "execution-fingerprint",
        "phase": "canonical",
        "case_id": result["id"],
        "answer_sha256": digest(answer),
        "evidence_sha256": digest(diagnostic),
        "reviewable": True,
        "reason": None,
    }
    review = verdict(subject)
    for field in (
        "run_id",
        "manifest_sha256",
        "execution_fingerprint",
        "phase",
        "case_id",
        "answer_sha256",
        "evidence_sha256",
    ):
        assert quality_verdicts.validate_verdict({**review, field: "stale"}, subject) is not None
    (report / "quality-verdicts.jsonl").write_text(json.dumps(review) + "\n", encoding="utf-8")
    assert quality_verdicts.main(["inspect", str(report)]) == 0
    accepted = json.loads(capsys.readouterr().out)
    assert accepted["quality"] == {"accepted": 1}
    assert accepted["execution"] == {"MANUAL_REVIEW": 1}
    assert {name: (report / name).read_bytes() for name in before} == before


def test_quality_overlay_legacy_and_skip_policy_are_explicit(quality_verdicts, tmp_path) -> None:  # type: ignore[no-untyped-def]
    report, manifest, _, _ = quality_fixture(quality_verdicts, tmp_path)
    legacy = {"phase": "canonical", "id": "legacy", "status": "PASS"}
    skipped = {
        "phase": "canonical",
        "id": "optional-capability",
        "manual_quality": False,
        "status": "SKIP",
    }
    aggregate = quality_verdicts.aggregate_quality(report, manifest, [legacy, skipped])

    assert aggregate["quality"] == {"not_required": 1, "unknown": 1}
    assert not quality_verdicts.quality_gate(aggregate, skip_policy="forbid")["passed"]
    assert quality_verdicts.quality_gate(
        aggregate,
        skip_policy="allow-with-rationale",
        skip_rationale="Optional capability is outside this coverage declaration.",
    )["passed"]


def test_quality_overlay_cli_is_offline_and_does_not_rewrite_execution_artifact(
    quality_verdicts, tmp_path, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    report, manifest, result, subject = quality_fixture(quality_verdicts, tmp_path)
    sidecar = report / "quality-verdicts.jsonl"
    sidecar.write_text(json.dumps(verdict(subject)) + "\n", encoding="utf-8")
    before_manifest = (report / "manifest.json").read_bytes()
    before_cases = (report / "cases.jsonl").read_bytes()
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: pytest.fail("process"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("network"))

    assert quality_verdicts.main(["gate", str(report), "--skip-policy", "forbid"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
    assert (report / "manifest.json").read_bytes() == before_manifest
    assert (report / "cases.jsonl").read_bytes() == before_cases
