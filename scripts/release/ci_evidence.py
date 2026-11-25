"""Select jobs and verify reusable results from GitHub's own push checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

WORKFLOWS = {
    "ci.yml": ("backend", "ui", "acceptance-extra", "worker", "android", "ios"),
    "windows.yml": ("windows-smoke",),
}
WINDOWS = ("windows-smoke", "backend", "ui", "worker", "acceptance-extra")
MOBILE = ("android", "ios")
ALL = frozenset(WINDOWS + MOBILE)
PUSH_BRANCHES = {"main", "codex/orion-r16-r18", "codex/orion-windows-acceptance"}
EVIDENCE_AGE = timedelta(hours=24)


def affected(paths: list[str]) -> set[str]:
    selection: set[str] = set()
    for path in paths:
        if path.startswith("scripts/android/"):
            selection.update(("android", "backend"))
        elif (
            path.startswith("ui/src-tauri/mobile/android/")
            or path == "ui/src-tauri/tauri.android.conf.json"
        ):
            selection.add("android")
        elif (
            path.startswith(("scripts/ios/", "ui/src-tauri/mobile/ios/"))
            or path == "ui/src-tauri/tauri.ios.conf.json"
        ):
            selection.add("ios")
        elif path in {
            "scripts/desktop/signed_update_fixture.py",
            "scripts/desktop/exercise-signed-update.ps1",
        }:
            selection.update(("windows-smoke", "backend"))
        elif path in {
            "docs/refactor/EXECUTION_LOG.md",
            "docs/refactor/PREVIEW_SIGNING.md",
            "docs/refactor/UPGRADE_8EB4AD2.md",
            "docs/refactor/CI_EVIDENCE.md",
            "docs/refactor/audit/FILE_REVIEW.csv",
            "docs/refactor/audit/INVENTORY.json",
            "docs/refactor/audit/SUMMARY.md",
        }:
            selection.add("acceptance-extra")
        else:
            # Shared code, workflow policy, lockfiles, build inputs and unknowns.
            return set(ALL)
    return selection


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], timeout=20)


def changed_since(candidate: str, target: str) -> set[str]:
    git("merge-base", "--is-ancestor", candidate, target)
    paths = git("diff", "--no-renames", "--name-only", "-z", candidate, target)
    return affected([part.decode("utf-8") for part in paths.split(b"\0") if part])


def api(path: str, **query):
    repo = os.environ["GITHUB_REPOSITORY"]
    suffix = "?" + urlencode(query) if query else ""
    return json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repo}/{path}{suffix}"], timeout=20
        )
    )


def push_runs(workflow: str, branch: str, **query):
    return api(
        f"actions/workflows/{workflow}/runs", event="push", branch=branch, **query
    )["workflow_runs"]


def run_jobs(run: dict) -> dict[str, dict]:
    jobs = api(f"actions/runs/{run['id']}/jobs", filter="latest", per_page=100)["jobs"]
    return {job["name"]: job for job in jobs}


def prior_successes(
    workflow: str, branch: str, target: str, required: set[str]
) -> dict[str, dict]:
    proofs = {}
    failed = set()
    cutoff = datetime.now(UTC) - EVIDENCE_AGE
    if not required:
        return proofs
    for run in push_runs(workflow, branch, status="completed", per_page=12):
        sha = run["head_sha"]
        if sha == target or datetime.fromisoformat(run["created_at"]) < cutoff:
            continue
        try:
            unaffected = required - changed_since(sha, target) - proofs.keys() - failed
        except (subprocess.CalledProcessError, UnicodeDecodeError):
            continue
        if not unaffected:
            continue
        for name, job in run_jobs(run).items():
            if name not in unaffected:
                continue
            if job["conclusion"] == "success":
                proofs[name] = {"sha": sha, "job": job["id"]}
            elif job["conclusion"] not in {"skipped", None}:
                failed.add(name)
        if proofs.keys() | failed >= required:
            break
    return proofs


def check(branch: str, target: str, required: tuple[str, ...], *, fresh: bool) -> None:
    deadline = time.monotonic() + 43 * 60
    while time.monotonic() < deadline:
        pending = set(required)
        for workflow, names in WORKFLOWS.items():
            selected = pending.intersection(names)
            if not selected:
                continue
            runs = push_runs(workflow, branch, head_sha=target, per_page=1)
            if not runs:
                continue
            jobs = run_jobs(runs[0])
            skipped = set()
            for name in selected:
                job = jobs.get(name)
                if not job or job["status"] != "completed":
                    continue
                if job["conclusion"] == "success":
                    pending.remove(name)
                elif job["conclusion"] == "skipped" and not fresh:
                    skipped.add(name)
                else:
                    raise SystemExit(
                        f"Required check {name} ended as {job['conclusion']} on {target}."
                    )
            if skipped:
                plan = jobs.get("plan", {})
                if plan.get("conclusion") != "success":
                    raise SystemExit(
                        f"{workflow} skipped required jobs without a successful plan."
                    )
                proofs = prior_successes(workflow, branch, target, skipped)
                if proofs.keys() != skipped:
                    raise SystemExit(
                        f"No compatible push evidence for {sorted(skipped - proofs.keys())}."
                    )
                print(json.dumps(proofs, sort_keys=True), flush=True)
                pending -= skipped
        if not pending:
            print(f"Verified {', '.join(required)} for {target}.", flush=True)
            return
        time.sleep(25)
    raise SystemExit(f"Required push jobs did not complete for {target}.")


def plan(workflow: str, target: str) -> None:
    required = WORKFLOWS[workflow]
    event = os.environ["GITHUB_EVENT_NAME"]
    branch = os.environ["GITHUB_REF_NAME"]
    proofs = {}
    if event == "pull_request":
        pull = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())[
            "pull_request"
        ]
        head = pull["head"]
        if (
            (head.get("repo") or {}).get("full_name") == os.environ["GITHUB_REPOSITORY"]
            and head["ref"] in PUSH_BRANCHES
            and same_tree(head["sha"], target)
        ):
            check(head["ref"], head["sha"], required, fresh=head["ref"] == "main")
            proofs = {
                key: {"sha": head["sha"], "source": "same-tree push"}
                for key in required
            }
        # Merge results that differ from the head get their own checks.
    elif event == "push" and branch != "main":
        try:
            proofs = prior_successes(workflow, branch, target, set(required))
        except (subprocess.SubprocessError, ValueError, KeyError) as error:
            print(
                f"Evidence unavailable ({type(error).__name__}); running full workflow.",
                flush=True,
            )
    print(
        json.dumps(
            {"reused": proofs, "run": sorted(set(required) - proofs.keys())},
            sort_keys=True,
        )
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.writelines(
            f"{name}={'false' if name in proofs else 'true'}\n" for name in required
        )


def same_tree(head: str, target: str) -> bool:
    try:
        return git("rev-parse", f"{head}^{{tree}}") == git(
            "rev-parse", f"{target}^{{tree}}"
        )
    except subprocess.SubprocessError:
        return False


def preview_needed(target: str) -> bool:
    try:
        for release in api("releases", per_page=50):
            tag = release["tag_name"]
            if (
                release["draft"]
                or not release["prerelease"]
                or not re.fullmatch(r"orion-preview-v\d+\.\d+\.\d+", tag)
            ):
                continue
            previous = git("rev-parse", f"refs/tags/{tag}^{{commit}}").decode().strip()
            return "windows-smoke" in changed_since(previous, target)
    except (subprocess.SubprocessError, ValueError, KeyError):
        pass
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "ci.yml",
            "windows.yml",
            "preview-windows",
            "preview-mobile",
            "stable",
        ),
    )
    args = parser.parse_args()
    target = git("rev-parse", "HEAD").decode().strip()
    if target != os.environ["GITHUB_SHA"]:
        raise SystemExit("CI checkout does not match the event SHA.")
    if args.mode in WORKFLOWS:
        plan(args.mode, target)
    else:
        required = {
            "preview-windows": WINDOWS,
            "preview-mobile": MOBILE,
            "stable": WINDOWS + MOBILE,
        }[args.mode]
        check(
            os.environ["GITHUB_REF_NAME"], target, required, fresh=args.mode == "stable"
        )
        if args.mode == "preview-windows":
            package = preview_needed(target)
            with Path(os.environ["GITHUB_OUTPUT"]).open(
                "a", encoding="utf-8"
            ) as output:
                output.write(f"package={'true' if package else 'false'}\n")


if __name__ == "__main__":
    main()
