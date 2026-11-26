"""Stable gates require actual manual CI success on the exact commit."""

import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize("conclusion", ["success", "skipped", "failure"])
def test_stable_gate_requires_manual_checks_at_exact_sha(monkeypatch, conclusion):
    path = Path(__file__).resolve().parents[2] / "scripts/release/ci_evidence.py"
    check = runpy.run_path(str(path))["check"]
    ci = check.__globals__

    def api(path, **query):
        if path.startswith("actions/workflows/"):
            assert query == dict(
                event="workflow_dispatch", branch="main", head_sha="target", per_page=1
            )
            workflow = path.split("/")[2]
            return {"workflow_runs": [{"id": workflow}]}
        workflow = path.split("/")[2]
        return {
            "jobs": [
                {"name": name, "status": "completed", "conclusion": conclusion}
                for name in ci["WORKFLOWS"][workflow]
            ]
        }

    monkeypatch.setitem(ci, "api", api)
    if conclusion == "success":
        check("main", "target")
    else:
        with pytest.raises(SystemExit, match=conclusion):
            check("main", "target")
