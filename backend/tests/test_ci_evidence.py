"""Release evidence must represent a real compatible GitHub push job."""

import json
import runpy
from datetime import UTC, datetime
from pathlib import Path

import pytest


@pytest.fixture
def ci():
    path = Path(__file__).resolve().parents[2] / "scripts/release/ci_evidence.py"
    return runpy.run_path(str(path))["check"].__globals__


def test_component_paths_and_shared_fallback(ci):
    assert ci["affected"](["ui/src-tauri/mobile/android/MainActivity.kt"]) == {"android"}
    assert ci["affected"](["scripts/android/smoke.py"]) == {"android", "backend"}
    assert ci["affected"](["ui/src-tauri/tauri.ios.conf.json"]) == {"ios"}
    assert ci["affected"](["scripts/desktop/signed_update_fixture.py"]) == {
        "backend",
        "windows-smoke",
    }
    for path in ("ui/package-lock.json", "scripts/new-input", ".github/workflows/ci.yml"):
        assert ci["affected"]([path]) == ci["ALL"]


def test_prior_evidence_requires_real_success_and_unchanged_inputs(ci, monkeypatch):
    run = {"head_sha": "ancestor", "created_at": datetime.now(UTC).isoformat()}
    monkeypatch.setitem(ci, "push_runs", lambda *_args, **_kwargs: [run])
    monkeypatch.setitem(ci, "changed_since", lambda *_: {"android"})
    monkeypatch.setitem(
        ci,
        "run_jobs",
        lambda _: {
            "android": {"conclusion": "success", "id": 1},
            "backend": {"conclusion": "skipped", "id": 2},
            "ui": {"conclusion": "success", "id": 3},
        },
    )
    assert ci["prior_successes"]("ci.yml", "branch", "head", {"android", "backend", "ui"}) == {
        "ui": {"sha": "ancestor", "job": 3}
    }


def test_newest_compatible_failure_requires_a_fresh_job(ci, monkeypatch):
    timestamp = datetime.now(UTC).isoformat()
    runs = [{"head_sha": sha, "created_at": timestamp} for sha in ("newer", "older")]
    monkeypatch.setitem(ci, "push_runs", lambda *_args, **_kwargs: runs)
    monkeypatch.setitem(ci, "changed_since", lambda *_: set())
    monkeypatch.setitem(
        ci,
        "run_jobs",
        lambda run: {
            "android": {"conclusion": "failure" if run == runs[0] else "success", "id": 1},
        },
    )
    assert ci["prior_successes"]("ci.yml", "branch", "head", {"android"}) == {}


@pytest.mark.parametrize("equal", [True, False])
def test_pr_reuses_push_only_for_the_same_tree(ci, monkeypatch, tmp_path, equal):
    event = tmp_path / "event.json"
    output = tmp_path / "output"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "head": {
                        "repo": {"full_name": "owner/orion"},
                        "ref": "codex/orion-windows-acceptance",
                        "sha": "head",
                    }
                }
            }
        )
    )
    for name, value in {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REF_NAME": "173/merge",
        "GITHUB_REPOSITORY": "owner/orion",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_OUTPUT": str(output),
    }.items():
        monkeypatch.setenv(name, value)
    checked = []
    monkeypatch.setitem(ci, "same_tree", lambda *_: equal)
    monkeypatch.setitem(ci, "check", lambda *args, **kwargs: checked.append(args))
    ci["plan"]("windows.yml", "merge")
    assert checked == (
        [("codex/orion-windows-acceptance", "head", ("windows-smoke",))] if equal else []
    )
    assert output.read_text().strip() == f"windows-smoke={'false' if equal else 'true'}"


@pytest.mark.parametrize(
    "fresh,result,accepted",
    [
        (False, "skipped", True),
        (True, "skipped", False),
        (False, "failure", False),
    ],
)
def test_gate_refuses_failed_current_checks_and_stable_requires_fresh(
    ci, monkeypatch, fresh, result, accepted
):
    monkeypatch.setitem(ci, "push_runs", lambda *_args, **_kwargs: [{}])
    monkeypatch.setitem(
        ci,
        "run_jobs",
        lambda _: {
            "plan": {"conclusion": "success"},
            "android": {"status": "completed", "conclusion": result},
        },
    )
    monkeypatch.setitem(ci, "prior_successes", lambda *_: {"android": {"job": 1}})
    if accepted:
        ci["check"]("branch", "head", ("android",), fresh=fresh)
    else:
        with pytest.raises(SystemExit, match=result):
            ci["check"]("branch", "head", ("android",), fresh=fresh)
