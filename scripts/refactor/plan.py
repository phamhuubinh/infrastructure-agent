"""Validate the refactor task graph or print ready work. Never executes tasks."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

VALID = {"todo", "in_progress", "needs_external", "done"}
REQUIRED_TASKS = {f"R{number:02}" for number in range(30)}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--next", action="store_true")
    mode.add_argument("--complete", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    state = json.loads((root / "docs/refactor/STATE.json").read_text(encoding="utf-8"))
    items = state["work_items"]
    indexed = {item["id"]: item for item in items}
    errors = []
    if len(indexed) != len(items):
        errors.append("Duplicate task IDs")
    missing_tasks = REQUIRED_TASKS - indexed.keys()
    if missing_tasks:
        errors.append(f"Missing mandatory tasks: {', '.join(sorted(missing_tasks))}")
    visiting, visited = set(), set()

    def visit(task_id):
        if task_id in visiting:
            errors.append(f"Dependency cycle at {task_id}")
            return
        if task_id in visited or task_id not in indexed:
            return
        visiting.add(task_id)
        for dependency in indexed[task_id]["depends_on"]:
            if dependency not in indexed:
                errors.append(f"{task_id}: unknown dependency {dependency}")
            else:
                visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for item in items:
        task_id = item["id"]
        visit(task_id)
        if item["status"] not in VALID:
            errors.append(f"{task_id}: invalid status")
        if item["status"] == "done":
            if not item["evidence"]:
                errors.append(f"{task_id}: Done without evidence")
            for evidence in item["evidence"]:
                if not isinstance(evidence, dict) or not all(
                    evidence.get(k) for k in ("kind", "result")
                ):
                    errors.append(f"{task_id}: evidence requires kind/result")
                    continue
                if evidence.get("path"):
                    target = (root / evidence["path"]).resolve()
                    if not target.is_relative_to(root) or not target.is_file():
                        errors.append(f"{task_id}: missing/out-of-scope evidence artifact")
                elif not str(evidence.get("url", "")).startswith("https://"):
                    errors.append(f"{task_id}: evidence requires local path or HTTPS URL")
            for dep in item["depends_on"]:
                if dep in indexed and indexed[dep]["status"] != "done":
                    errors.append(f"{task_id}: Done while prerequisite {dep} is not Done")
        if item["status"] == "needs_external" and not item["blockers"]:
            errors.append(f"{task_id}: needs_external without specific blocker")
        if item["status"] == "in_progress":
            for dep in item["depends_on"]:
                if indexed.get(dep, {}).get("status") != "done":
                    errors.append(f"{task_id}: started before prerequisite {dep} is Done")
    ready = [
        {"id": item["id"], "title": item["title"], "status": item["status"]}
        for item in items if item["status"] in {"todo", "in_progress"}
        and all(indexed.get(dep, {}).get("status") == "done" for dep in item["depends_on"])
    ]
    review_required = args.complete or any(
        indexed.get(task_id, {}).get("status") == "done" for task_id in ("R01", "R19")
    )
    if review_required:
        review_flags = ["--require-reviewed"]
        if args.complete or indexed.get("R19", {}).get("status") == "done":
            review_flags.append("--require-final")
        inventory = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).with_name("inventory.py")),
             "--root", str(root), "--check", *review_flags],
            check=False, capture_output=True, text=True, encoding="utf-8",
        )
        if inventory.returncode:
            errors.append("Inventory coverage/hash/removal/semantic review is not complete")
    if args.complete:
        for item in items:
            if item["status"] != "done":
                errors.append(f"{item['id']}: not Done")
    print(json.dumps({
        "phase": state["phase"], "ready": ready if args.next and not errors else [],
        "needs_external": [
            {"id": item["id"], "blockers": item["blockers"]}
            for item in items if item["status"] == "needs_external"
        ],
        "errors": errors,
    }, ensure_ascii=False, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
