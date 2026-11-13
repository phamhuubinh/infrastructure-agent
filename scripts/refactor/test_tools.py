"""Offline regression tests for the audit/task completion gates.

Run with Python 3.12+: python -B -m unittest discover -s scripts/refactor -p test_tools.py -v
All fixtures live in temporary repositories, never in the user's checkout.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import inventory

SCRIPTS = Path(__file__).resolve().parent


class AuditGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="orion-audit-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_git("init", "-q")
        self.run_git("-c", "user.name=Test", "-c", "user.email=test@invalid",
                     "commit", "--allow-empty", "-qm", "fixture")
        (self.root / "source.py").write_text("print('fixture')\n", encoding="utf-8")

    def run_git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True)

    def invoke(self, script, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / script), "--root", str(self.root), *args],
            check=False, capture_output=True, text=True, encoding="utf-8",
        )
        return result

    @property
    def ledger(self):
        return self.root / "docs/refactor/audit/FILE_REVIEW.csv"

    def read_rows(self):
        with self.ledger.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def write_rows(self, rows):
        with self.ledger.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=inventory.FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def approve(self, **overrides):
        rows = self.read_rows()
        for row in rows:
            row.update(review_status="reviewed", final_action="keep",
                       reason="Fixture approved by test", replacement_or_callers="Fixture entry",
                       verification="Fixture inspected")
            row.update(overrides)
        self.write_rows(rows)

    def test_inventory_is_not_semantic_approval(self):
        self.assertEqual(self.invoke("inventory.py", "--write").returncode, 0)
        self.assertEqual(self.invoke("inventory.py", "--check").returncode, 0)
        denied = self.invoke("inventory.py", "--check", "--require-reviewed")
        self.assertEqual(denied.returncode, 1)
        self.assertEqual(json.loads(denied.stdout)["semantic_review_remaining"], 1)
        self.approve()
        self.assertEqual(self.invoke("inventory.py", "--check", "--require-reviewed").returncode, 0)

    def test_provider_credential_store_is_metadata_only_without_reading_payload(self):
        secret = self.root / "state" / "provider-credentials" / ("a" * 32 + ".json")
        secret.parent.mkdir(parents=True)
        secret.write_bytes(b"fixture-private-payload")
        original_read = Path.read_bytes
        def guarded_read(path):
            if path == secret:
                self.fail("Inventory read a credential payload")
            return original_read(path)
        with patch.object(Path, "read_bytes", guarded_read):
            rows, errors = inventory.collect(self.root)
        self.assertEqual(errors, [])
        row = next(row for row in rows if row["path"] == secret.relative_to(self.root).as_posix())
        self.assertEqual(row["kind"], "private_metadata_only")
        self.assertEqual(row["sha256"], "")

    def test_changed_file_invalidates_approval(self):
        self.invoke("inventory.py", "--write")
        self.approve()
        (self.root / "source.py").write_text("print('changed')", encoding="utf-8")
        self.assertEqual(self.invoke("inventory.py", "--check").returncode, 1)
        self.invoke("inventory.py", "--write")
        self.assertEqual(self.read_rows()[0]["review_status"], "unreviewed")

    def test_local_build_output_is_excluded_but_tracked_content_is_reviewed(self):
        local = self.root / "ui/node_modules/generated.txt"
        local.parent.mkdir(parents=True)
        local.write_text("local dependency")
        native_output = self.root / "ui/src-tauri/target/generated.txt"
        native_output.parent.mkdir(parents=True)
        native_output.write_text("local native build output")
        android_output = self.root / "ui/src-tauri/gen/android/app/build.gradle.kts"
        android_output.parent.mkdir(parents=True)
        android_output.write_text("generated Android project")
        tracked = self.root / "ui/dist/tracked.txt"
        tracked.parent.mkdir(parents=True)
        tracked.write_text("committed fixture")
        self.run_git("add", "ui/dist/tracked.txt")
        rows, errors = inventory.collect(self.root)
        self.assertFalse(errors)
        self.assertEqual({row["path"] for row in rows}, {"source.py", "ui/dist/tracked.txt"})
        self.run_git("add", android_output.relative_to(self.root).as_posix())
        rows, errors = inventory.collect(self.root)
        self.assertFalse(errors)
        self.assertIn(android_output.relative_to(self.root).as_posix(), {row["path"] for row in rows})

    def test_retired_record_is_preserved_and_requires_removal_reason(self):
        self.invoke("inventory.py", "--write")
        self.approve()
        (self.root / "source.py").unlink()
        self.assertEqual(self.invoke("inventory.py", "--check").returncode, 1)
        self.invoke("inventory.py", "--write")
        self.assertEqual(self.read_rows()[0]["kind"], "removed_file_record")
        self.approve(final_action="remove")
        self.assertEqual(self.invoke("inventory.py", "--check", "--require-reviewed").returncode, 0)

    def test_duplicate_ledger_is_not_silently_overwritten(self):
        self.invoke("inventory.py", "--write")
        rows = self.read_rows()
        self.write_rows(rows + rows)
        before = self.ledger.read_bytes()
        self.assertNotEqual(self.invoke("inventory.py", "--write").returncode, 0)
        self.assertEqual(before, self.ledger.read_bytes())

    def test_planned_removal_is_allowed_in_initial_audit_but_not_final_cleanup(self):
        self.invoke("inventory.py", "--write")
        self.approve(final_action="remove")
        self.assertEqual(self.invoke("inventory.py", "--check", "--require-reviewed").returncode, 0)
        self.assertEqual(self.invoke("inventory.py", "--check", "--require-final").returncode, 1)

    def test_private_data_is_not_hashed_and_requires_preservation(self):
        (self.root / ".env.production").write_text("TOKEN=fixture-private", encoding="utf-8")
        (self.root / "data.sqlite-wal").write_bytes(b"fixture-private")
        self.invoke("inventory.py", "--write")
        rows = {r["path"]: r for r in self.read_rows()}
        for name in (".env.production", "data.sqlite-wal"):
            self.assertEqual(rows[name]["kind"], "private_metadata_only")
            self.assertEqual(rows[name]["sha256"], "")
            rows[name].update(review_status="reviewed", final_action="remove",
                              reason="fixture", replacement_or_callers="fixture", verification="fixture")
            self.assertIsNotNone(inventory.review_issue(rows[name]))
        report = (self.ledger.parent / "INVENTORY.json").read_text(encoding="utf-8")
        self.assertNotIn("fixture-private", report)
        self.assertFalse(inventory.private(".env.example"))
        self.assertTrue(inventory.private("servers.json"))
        self.assertTrue(inventory.private("docker-compose.env"))

    def test_traversal_errors_fail_closed(self):
        def inaccessible(*args, **kwargs):
            kwargs["onerror"](PermissionError("fixture"))
            return iter(())

        with patch.object(inventory.os, "walk", side_effect=inaccessible):
            rows, errors = inventory.collect(self.root)
        self.assertEqual(rows, [])
        self.assertTrue(errors)

    def test_directory_link_boundary_is_never_followed(self):
        # Junctions do not require Windows symlink privileges.
        with tempfile.TemporaryDirectory(prefix="orion-outside-") as external:
            outside = Path(external)
            (outside / "secret.txt").write_text("outside fixture", encoding="utf-8")
            link = self.root / "linked"
            if os.name == "nt":
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                                        check=False, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.addCleanup(lambda: link.rmdir() if link.exists() else None)
            else:
                link.symlink_to(outside, target_is_directory=True)
            rows, errors = inventory.collect(self.root)
            self.assertFalse(errors)
            linked = [r for r in rows if r["path"].startswith("linked")]
            self.assertEqual(len(linked), 1)
            self.assertEqual(linked[0]["kind"], "symlink_not_followed")
            self.assertTrue(linked[0]["sha256"])
            if os.name == "nt":
                link.rmdir()

    def test_linked_output_directory_is_rejected_without_external_writes(self):
        with tempfile.TemporaryDirectory(prefix="orion-output-outside-") as external:
            destination = self.root / "docs"
            if os.name == "nt":
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(destination), external],
                    check=False, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                destination.symlink_to(external, target_is_directory=True)
            try:
                result = self.invoke("inventory.py", "--write")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(list(Path(external).iterdir()), [])
            finally:
                if os.name == "nt":
                    destination.rmdir()
                else:
                    destination.unlink()

    def test_done_audit_cannot_unlock_tasks_with_unreviewed_files(self):
        state_path = self.root / "docs/refactor/STATE.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {"phase": "test", "work_items": [
            {"id": "R01", "title": "Audit", "depends_on": [], "status": "done",
             "evidence": [{"kind": "test", "path": "source.py", "result": "fixture"}],
             "blockers": []},
            {"id": "R02", "title": "Core", "depends_on": ["R01"], "status": "todo",
             "evidence": [], "blockers": []},
        ]}
        for number in range(30):
            task_id = f"R{number:02}"
            if task_id not in {"R01", "R02"}:
                state["work_items"].append({
                    "id": task_id, "title": "Fixture", "depends_on": [], "status": "todo",
                    "evidence": [], "blockers": [],
                })
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.invoke("inventory.py", "--write")
        denied = self.invoke("plan.py", "--next")
        self.assertEqual(denied.returncode, 1)
        self.assertEqual(json.loads(denied.stdout)["ready"], [])
        self.approve()
        ready = self.invoke("plan.py", "--next")
        self.assertEqual(ready.returncode, 0, ready.stderr)
        self.assertIn("R02", [r["id"] for r in json.loads(ready.stdout)["ready"]])

    def test_mandatory_gates_cannot_be_dropped_from_state(self):
        state_path = self.root / "docs/refactor/STATE.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"phase": "test", "work_items": []}), encoding="utf-8")
        result = self.invoke("plan.py", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("R29", result.stdout)

    def test_unmet_dependencies_and_external_blockers_are_enforced(self):
        state_path = self.root / "docs/refactor/STATE.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        items = [{"id": f"R{number:02}", "title": "Fixture", "depends_on": [],
                  "status": "todo", "evidence": [], "blockers": []} for number in range(30)]
        items[2].update(status="in_progress", depends_on=["R01"])
        items[28].update(status="needs_external")
        state_path.write_text(json.dumps({"phase": "test", "work_items": items}), encoding="utf-8")
        result = self.invoke("plan.py", "--next")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["ready"], [])
        self.assertTrue(any("started before" in e for e in report["errors"]))
        self.assertTrue(any("specific blocker" in e for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
