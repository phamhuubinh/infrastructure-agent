"""Managed-data snapshots, restore failures and exact owned retention."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing

import pytest
from conftest import ScriptedBackend
from pydantic import SecretStr

from orion.bootstrap import build_application
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.service import KnowledgeService
from orion.models.credential_store import ProtectedFileCredentialStore
from orion.persistence import backup
from orion.persistence.ownership import RuntimeLease
from orion.persistence.sqlite import SQLiteStore


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    database = root / "custom.db"
    store = SQLiteStore(database)
    session = store.create_session()
    knowledge = KnowledgeService(store, LocalBlobStore(root / "blobs"))
    uploaded = knowledge.attach(session, "hello.txt", "private Unicode 你好".encode())
    credentials = ProtectedFileCredentialStore(root / "provider-credentials")
    reference = credentials.put(SecretStr("test-only-secret"))
    store.upsert_model_config(
        "openai_compatible", "http://model.test/v1", "fake", None, credential_ref=reference
    )
    request = store.create_request(session)
    store.close()
    bundles = tmp_path / "backups"
    bundles.mkdir()
    return database, bundles, session, uploaded, reference, request


def test_full_backup_restore_and_normal_startup(data, tmp_path):
    database, bundles, session, uploaded, reference, request = data
    bundle = backup.export_bundle(database, bundles)
    manifest = backup.validate_bundle(bundle)
    assert manifest["environment_credentials"] == []
    assert len(manifest["files"]) == 3
    assert b"test-only-secret" not in (bundle / "manifest.json").read_bytes()
    target = tmp_path / "restored"
    restored_db = backup.import_bundle(bundle, target)
    credentials = ProtectedFileCredentialStore(target / "provider-credentials")
    assert credentials.resolve(reference).get_secret_value() == "test-only-secret"
    restored = SQLiteStore(restored_db)
    try:
        document = restored.document(uploaded.document.document_id)
        assert document["session_id"] == session
        assert LocalBlobStore(target / "blobs").get(document["blob_id"]) == (
            "private Unicode 你好".encode()
        )
        assert restored.request(request)["status"] == "queued"
    finally:
        restored.close()
    backend = ScriptedBackend([])
    application = build_application(restored_db, backend=backend, seed_model_from_environment=False)
    try:
        assert application.store.request(request)["status"] == "failed"
        assert backend.calls == []
    finally:
        application.store.close()
    # Backup/import are storage operations, never dispatch/recover a request.
    with sqlite3.connect(database) as original:
        assert original.execute("SELECT status FROM requests").fetchone()[0] == "queued"


def test_export_refuses_active_runtime_and_preserves_data(data):
    database, bundles, *_ = data
    lease = RuntimeLease(database)
    try:
        with pytest.raises(RuntimeError, match="another Orion runtime"):
            backup.export_bundle(database, bundles)
        assert list(bundles.iterdir()) == []
    finally:
        lease.close()


def test_import_refuses_existing_target(data, tmp_path):
    database, bundles, *_ = data
    bundle = backup.export_bundle(database, bundles)
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep").write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        backup.import_bundle(bundle, target)
    assert (target / "keep").read_bytes() == b"keep"


@pytest.mark.parametrize(
    "fault",
    [
        "checksum",
        "extra",
        "missing",
        "version",
        "traversal",
        "duplicate",
        "foreign-key",
        "credential",
    ],
)
def test_invalid_bundle_cannot_publish_restore(data, tmp_path, fault):
    database, bundles, *_ = data
    bundle = backup.export_bundle(database, bundles)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if fault == "checksum":
        (bundle / "orion.db").write_bytes(b"not a database")
    elif fault == "extra":
        backup._write(bundle / "unexpected", b"surprise")
    elif fault == "missing":
        next((bundle / "blobs").iterdir()).unlink()
    elif fault == "version":
        manifest["version"] = 100
    elif fault == "traversal":
        manifest["files"]["../escape"] = {"size": 0, "sha256": "0" * 64}
    elif fault == "duplicate":
        manifest_path.write_text('{"version":1,"version":1}')
    elif fault == "foreign-key":
        with closing(sqlite3.connect(bundle / "orion.db")) as connection:
            connection.execute("UPDATE documents SET session_id='absent'")
            connection.commit()
        manifest["files"]["orion.db"] = backup._fingerprint(bundle / "orion.db")
    elif fault == "credential":
        path = next((bundle / "provider-credentials").iterdir())
        path.write_bytes(b"invalid credential")
        manifest["files"][f"provider-credentials/{path.name}"] = backup._fingerprint(path)
    if fault != "duplicate":
        manifest_path.write_text(json.dumps(manifest))
    target = tmp_path / "restored"
    with pytest.raises((OSError, ValueError, RuntimeError, sqlite3.Error)):
        backup.import_bundle(bundle, target)
    assert not target.exists()


def test_missing_live_blob_fails_export_without_publishing(data):
    database, bundles, *_ = data
    next((database.parent / "blobs").iterdir()).unlink()
    with pytest.raises(ValueError, match="missing a document blob"):
        backup.export_bundle(database, bundles)
    assert not list(bundles.glob("orion-backup-*"))
    assert len(list(bundles.glob(".orion-export-*"))) == 1


def test_hardlinked_blob_rejected_by_export(data, tmp_path):
    database, bundles, *_ = data
    blob = next((database.parent / "blobs").iterdir())
    os.link(blob, tmp_path / "alias")
    with pytest.raises(OSError):
        backup.export_bundle(database, bundles)
    assert blob.read_bytes() == "private Unicode 你好".encode()


def test_restore_copy_failure_never_publishes(data, tmp_path, monkeypatch):
    database, bundles, *_ = data
    bundle = backup.export_bundle(database, bundles)

    def fail(*args):
        raise OSError("injected write failure")

    monkeypatch.setattr(backup, "_copy", fail)
    target = tmp_path / "restored"
    with pytest.raises(OSError, match="injected"):
        backup.import_bundle(bundle, target)
    assert not target.exists()
    assert backup.validate_bundle(bundle)["version"] == 1


def test_retention_keeps_newest_and_preserves_unrelated_data(data):
    database, bundles, *_ = data
    oldest = backup.export_bundle(database, bundles)
    newest = backup.export_bundle(database, bundles)
    unrelated = bundles / "unrelated"
    unrelated.mkdir()
    (unrelated / "keep").write_bytes(b"keep")
    assert backup.retain_bundles(bundles, keep=1) == (oldest,)
    assert not oldest.exists() and newest.is_dir()
    assert (unrelated / "keep").read_bytes() == b"keep"
    assert database.exists()


def test_retention_preflight_prevents_partial_deletion(data):
    database, bundles, *_ = data
    first = backup.export_bundle(database, bundles)
    second = backup.export_bundle(database, bundles)
    backup._write(first / "unknown", b"leave everything")
    with pytest.raises(ValueError):
        backup.retain_bundles(bundles, keep=1)
    assert first.is_dir() and second.is_dir()
    for keep in (0, -1, True):
        with pytest.raises(ValueError):
            backup.retain_bundles(bundles, keep=keep)


def test_environment_refs_are_requirements_not_exported_values(data, monkeypatch):
    database, bundles, *_ = data
    monkeypatch.setenv("BACKUP_TEST_SECRET", "environment-value-must-not-be-exported")
    store = SQLiteStore(database)
    store.upsert_model_config(
        "openai_compatible",
        "http://model.test/v1",
        "fake",
        None,
        credential_ref="env:BACKUP_TEST_SECRET",
    )
    store.close()
    bundle = backup.export_bundle(database, bundles)
    manifest = backup.validate_bundle(bundle)
    assert manifest["environment_credentials"] == ["env:BACKUP_TEST_SECRET"]
    for name in ["manifest.json", *manifest["files"]]:
        assert b"environment-value-must-not-be-exported" not in (bundle / name).read_bytes()


def test_missing_referenced_credential_fails_export(data):
    database, bundles, *_ = data
    next((database.parent / "provider-credentials").iterdir()).unlink()
    with pytest.raises(ValueError, match="missing a provider credential"):
        backup.export_bundle(database, bundles)
    assert not list(bundles.glob("orion-backup-*"))


def test_cross_platform_protected_credential_restore_fails(data, tmp_path):
    database, bundles, *_ = data
    bundle = backup.export_bundle(database, bundles)
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["platform"] = "linux" if os.name == "nt" else "win32"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="original operating system/account"):
        backup.import_bundle(bundle, tmp_path / "restored")


def test_bundle_privacy_is_verified_before_retention(data):
    database, bundles, *_ = data
    first = backup.export_bundle(database, bundles)
    second = backup.export_bundle(database, bundles)
    if os.name == "nt":
        import subprocess

        subprocess.run(
            ["icacls", str(first), "/grant", "*S-1-1-0:(RX)"], check=True, capture_output=True
        )
    else:
        first.chmod(0o755)
    with pytest.raises(OSError, match="private"):
        backup.retain_bundles(bundles, keep=1)
    assert first.is_dir() and second.is_dir()


def test_data_cli_roundtrip_and_failure_do_not_leak_secrets(data, tmp_path, monkeypatch, capsys):
    from orion import cli

    database, bundles, *_ = data
    monkeypatch.setenv("ORION_DATABASE_PATH", str(database))
    monkeypatch.setattr("sys.argv", ["orion", "data", "export", str(bundles)])
    cli.main()
    bundle = json.loads(capsys.readouterr().out)["bundle"]
    target = tmp_path / "restored"
    monkeypatch.setattr("sys.argv", ["orion", "data", "import", bundle, str(target)])
    cli.main()
    assert json.loads(capsys.readouterr().out)["database"] == str(target / "orion.db")
    monkeypatch.setattr("sys.argv", ["orion", "data", "import", bundle, str(target)])
    with pytest.raises(SystemExit, match="Data operation failed") as failure:
        cli.main()
    assert "test-only-secret" not in str(failure.value)
