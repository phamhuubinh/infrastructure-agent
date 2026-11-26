"""Windows update rollback and version ordering regressions."""

from __future__ import annotations

import base64
import json
import runpy
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from orion.access.owner import OwnerAuth, totp_code
from orion.api.app import create_app
from orion.cli.upgrade_snapshot import check_database, copy_checked, inventory, restore_folders
from orion.models.credential_store import ProtectedFileCredentialStore
from orion.persistence.sqlite import SQLiteStore

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI release fixture")
@pytest.mark.parametrize("rollback", [False, True], ids=["startup", "rollback"])
def test_release_fixture_survives_managed_startup_and_rollback(tmp_path, rollback):
    fixture = runpy.run_path(str(ROOT / "scripts/desktop/signed_update_fixture.py"))
    live = tmp_path / "managed"
    fixture["seed_fixture"](live)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    copy_checked(live, snapshot / "managed")
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {"database_tables": check_database(live / "orion.db"), "files": inventory(snapshot)}
        ),
        encoding="utf-8",
    )
    if rollback:
        (live / "orion.db").write_bytes(b"injected failure")
        restore_folders(((snapshot / "managed", live),))
    with TestClient(
        create_app(live / "orion.db", managed_desktop=True, update_pending=True)
    ) as client:
        assert client.get("/api/health").status_code == 200
    fixture["verify_fixture"](live, snapshot)
    store = SQLiteStore(live / "orion.db")
    try:
        store.create_project("Unexpected project mutation")
    finally:
        store.close()
    with pytest.raises(RuntimeError, match=r"changed=\['projects'\]"):
        fixture["verify_fixture"](live, snapshot)


def test_versions_are_increasing_across_stable_and_preview():
    allocate = runpy.run_path(str(ROOT / "scripts/release/desktop_version.py"))["allocate"]
    published = ["v0.1.4", "orion-preview-v0.1.10", "unrelated"]
    assert allocate("0.1.5", published) == "0.1.11"
    assert allocate("0.1.65535", []) == "0.2.0"
    assert allocate("0.1.11", published, "0.1.11") == "0.1.11"
    with pytest.raises(ValueError, match="exceed"):
        allocate("0.1.10", published, "0.1.10")
    with pytest.raises(ValueError, match="Windows"):
        allocate("0.1.65536", [])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI update snapshot")
def test_failed_update_restores_copied_history_projects_dpapi_and_mfa(tmp_path):
    data = tmp_path / "managed"
    data.mkdir()
    store = SQLiteStore(data / "orion.db")
    try:
        owner = OwnerAuth(store)
        pending, uri = owner.start_setup(secrets.token_urlsafe(24))
        key = parse_qs(urlsplit(uri).query)["secret"][0]
        owner.confirm_setup(
            pending,
            totp_code(base64.b32decode(key + "=" * (-len(key) % 8)), int(time.time() // 30)),
            rotation=False,
        )
        project_id = store.create_project("Rollback fixture")["project_id"]
        session_id = store.create_session(project_id=project_id)
        store.append_timeline(session_id, None, "user_message", {"content": "Keep this history"})
        value = SecretStr(secrets.token_urlsafe(24))
        reference = ProtectedFileCredentialStore(data / "provider-credentials").put(value)
    finally:
        store.close()
    installed = tmp_path / "Orion"
    installed.mkdir()
    (installed / "Orion.exe").write_bytes(b"previous binary fixture")
    backup = tmp_path / "backup"
    backup.mkdir()
    copy_checked(data, backup / "managed")
    copy_checked(installed, backup / "installed")
    before = check_database(backup / "managed/orion.db")
    (data / "orion.db").write_bytes(b"injected corruption")
    (installed / "Orion.exe").write_bytes(b"invalid update fixture")
    restore_folders(((backup / "installed", installed), (backup / "managed", data)))
    assert (installed / "Orion.exe").read_bytes() == b"previous binary fixture"
    assert check_database(data / "orion.db") == before
    assert ProtectedFileCredentialStore(data / "provider-credentials").resolve(reference) == value
    failed = next(tmp_path.glob("managed.failed-update-*"))
    assert (failed / "orion.db").read_bytes() == b"injected corruption"


def test_failed_second_swap_reinstates_first_target(tmp_path, monkeypatch):
    pairs = []
    for label in ("app", "managed"):
        source, target = tmp_path / f"{label}-backup", tmp_path / label
        for directory, content in ((source, "backup"), (target, "before")):
            directory.mkdir()
            (directory / "fixture").write_text(content, encoding="utf-8")
        pairs.append((source, target))

    rename = Path.rename

    def fail_second_replacement(self, target):
        if self.name.startswith("managed.restore-") and target == pairs[1][1]:
            raise OSError("swap failed")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_second_replacement)
    with pytest.raises(OSError, match="swap failed"):
        restore_folders(tuple(pairs))
    assert all((target / "fixture").read_text() == "before" for _, target in pairs)
