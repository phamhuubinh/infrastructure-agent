"""Verify manually dispatched checks for the exact Stable release commit."""

from __future__ import annotations

import json
import os
import subprocess
import time
from urllib.parse import urlencode

WORKFLOWS = {
    "ci.yml": {"backend", "ui", "acceptance-extra", "worker", "android", "ios"},
    "windows.yml": {"windows-smoke"},
}


def api(path: str, **query):
    repo = os.environ["GITHUB_REPOSITORY"]
    return json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repo}/{path}?{urlencode(query)}"], timeout=20
        )
    )


def check(branch: str, target: str) -> None:
    deadline = time.monotonic() + 43 * 60
    while time.monotonic() < deadline:
        pending = set().union(*WORKFLOWS.values())
        for workflow, names in WORKFLOWS.items():
            runs = api(
                f"actions/workflows/{workflow}/runs",
                event="workflow_dispatch",
                branch=branch,
                head_sha=target,
                per_page=1,
            )["workflow_runs"]
            if not runs:
                continue
            jobs = api(
                f"actions/runs/{runs[0]['id']}/jobs", filter="latest", per_page=100
            )["jobs"]
            completed = set()
            for job in jobs:
                name = job["name"]
                if name not in names or job["status"] != "completed":
                    continue
                if job["conclusion"] != "success":
                    raise SystemExit(
                        f"Required check {name} ended as {job['conclusion']} on {target}."
                    )
                completed.add(name)
            pending -= completed
        if not pending:
            print(f"Verified manually dispatched CI for {target}.", flush=True)
            return
        time.sleep(25)
    raise SystemExit(f"Required manual CI jobs did not complete for {target}.")


if __name__ == "__main__":
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != os.environ["GITHUB_SHA"]:
        raise SystemExit("CI checkout does not match the event SHA.")
    check(os.environ["GITHUB_REF_NAME"], head)
