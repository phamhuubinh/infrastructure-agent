"""Offline, versioned managed-data bundles; never overwrite deployed data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from orion.models.credential_store import ProtectedFileCredentialStore
from orion.persistence.ownership import RuntimeLease
from orion.persistence.private_files import (
    checked_path,
    create_private_directory,
    create_private_file,
    open_checked_file,
    open_private_file,
    require_private_path,
)

MANIFEST_LIMIT = 16 * 1024 * 1024
MAX_FILES = 100_000
MAX_TOTAL_BYTES = 1024**4
_PREFIX = "orion-backup-"


def _opaque_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


@contextmanager
def _lease(path: Path) -> Iterator[None]:
    lease = RuntimeLease(path)
    try:
        yield
    finally:
        lease.close()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write(path: Path, content: bytes) -> None:
    with os.fdopen(open_private_file(path), "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def _copy(source: Path, target: Path) -> None:
    with os.fdopen(open_checked_file(source), "rb") as incoming:
        if os.fstat(incoming.fileno()).st_size > MAX_TOTAL_BYTES:
            raise ValueError("Backup file exceeds supported size")
        with os.fdopen(open_private_file(target), "wb") as outgoing:
            copied = 0
            while block := incoming.read(1024 * 1024):
                copied += len(block)
                if copied > MAX_TOTAL_BYTES:
                    raise ValueError("Backup file exceeds supported size")
                outgoing.write(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())


def _fingerprint(path: Path) -> dict[str, int | str]:
    digest, size = hashlib.sha256(), 0
    with os.fdopen(open_checked_file(path), "rb") as source:
        while block := source.read(1024 * 1024):
            size += len(block)
            if size > MAX_TOTAL_BYTES:
                raise ValueError("Backup file exceeds supported size")
            digest.update(block)
    return {"size": size, "sha256": digest.hexdigest()}


def _read_manifest(path: Path) -> dict[str, Any]:
    with os.fdopen(open_checked_file(path), "rb") as source:
        data = source.read(MANIFEST_LIMIT + 1)
    if len(data) > MANIFEST_LIMIT:
        raise ValueError("Backup manifest exceeds supported size")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate backup manifest key")
            result[key] = value
        return result

    value = json.loads(data, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Invalid backup manifest")
    return value


def _payload_name(name: str) -> bool:
    parts = PurePosixPath(name).parts
    if name == "orion.db":
        return True
    if len(parts) != 2 or str(PurePosixPath(name)) != name:
        return False
    folder, identity = parts
    return (folder == "blobs" and _opaque_uuid(identity)) or (
        folder == "provider-credentials" and bool(re.fullmatch(r"[0-9a-f]{32}\.json", identity))
    )


def _database_metadata(path: Path, files: set[str]) -> tuple[str, list[str]]:
    checked_path(path)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Backup database integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Backup database foreign keys are invalid")
        schema = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = {row[1] for row in schema if row[0] == "table"}
        if not {"sessions", "requests", "documents", "model_configs"} <= tables:
            raise ValueError("Backup database schema is unsupported")
        for (blob_id,) in connection.execute(
            "SELECT DISTINCT blob_id FROM documents WHERE deleted_at IS NULL"
        ):
            if not isinstance(blob_id, str) or f"blobs/{blob_id}" not in files:
                raise ValueError("Backup is missing a document blob")
        references: set[str] = set()
        for reference, profile in connection.execute(
            "SELECT credential_ref, profile_json FROM model_configs"
        ):
            if reference is not None:
                if not isinstance(reference, str):
                    raise ValueError("Backup credential reference is invalid")
                references.add(reference)
            if profile:
                parsed = json.loads(profile)
                if not isinstance(parsed, dict):
                    raise ValueError("Backup profile is invalid")
                reference = parsed.get("credential_ref")
                if reference is not None:
                    if not isinstance(reference, str):
                        raise ValueError("Backup credential reference is invalid")
                    references.add(reference)
        environment = []
        for reference in sorted(references):
            if re.fullmatch(r"secret:[0-9a-f]{32}", reference):
                if f"provider-credentials/{reference[7:]}.json" not in files:
                    raise ValueError("Backup is missing a provider credential")
            elif re.fullmatch(r"env:[A-Za-z_][A-Za-z0-9_]*", reference):
                environment.append(reference)
            else:
                raise ValueError("Backup credential reference is unsupported")
    return hashlib.sha256(_json_bytes(schema)).hexdigest(), environment


def validate_bundle(bundle: Path, *, check_credentials: bool = True) -> dict[str, Any]:
    """Validate the exact closed bundle before import or retention; no extraction."""
    bundle = bundle.absolute()
    require_private_path(bundle, directory=True)
    require_private_path(bundle / "manifest.json")
    manifest = _read_manifest(bundle / "manifest.json")
    expected = {
        "format",
        "version",
        "id",
        "created_at",
        "platform",
        "schema_sha256",
        "environment_credentials",
        "files",
    }
    if (
        set(manifest) != expected
        or manifest["format"] != "orion-managed-data"
        or type(manifest["version"]) is not int
        or manifest["version"] != 1
        or not isinstance(manifest["id"], str)
        or not _opaque_uuid(manifest["id"])
        or bundle.name != _PREFIX + manifest["id"]
        or not isinstance(manifest["platform"], str)
        or manifest["platform"] not in {"win32", "linux", "darwin"}
        or not isinstance(manifest["created_at"], str)
    ):
        raise ValueError("Unsupported backup manifest")
    created = datetime.fromisoformat(manifest["created_at"])
    if created.tzinfo is None or created.utcoffset() != UTC.utcoffset(created):
        raise ValueError("Backup timestamp must be UTC")
    files = manifest["files"]
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES or "orion.db" not in files:
        raise ValueError("Invalid backup inventory")
    total = 0
    for name, record in files.items():
        if (
            not _payload_name(name)
            or not isinstance(record, dict)
            or set(record) != {"size", "sha256"}
            or type(record["size"]) is not int
            or record["size"] < 0
            or not isinstance(record["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
        ):
            raise ValueError("Invalid backup file record")
        total += record["size"]
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Backup exceeds supported size")
    actual = set()
    for item in bundle.iterdir():
        if item.name in {"blobs", "provider-credentials"}:
            require_private_path(item, directory=True)
            for child in item.iterdir():
                require_private_path(child)
                actual.add(f"{item.name}/{child.name}")
        else:
            require_private_path(item)
            actual.add(item.name)
    if actual != set(files) | {"manifest.json"}:
        raise ValueError("Backup contains missing or unexpected files")
    for name, record in files.items():
        if _fingerprint(bundle / name) != record:
            raise ValueError("Backup file checksum mismatch")
    schema, environment = _database_metadata(bundle / "orion.db", set(files))
    if schema != manifest["schema_sha256"] or environment != manifest["environment_credentials"]:
        raise ValueError("Backup database metadata mismatch")
    credential_files = [name for name in files if name.startswith("provider-credentials/")]
    if check_credentials and credential_files:
        if manifest["platform"] != sys.platform:
            raise ValueError("Protected credentials require the original operating system/account")
        store = ProtectedFileCredentialStore(bundle / "provider-credentials")
        for name in credential_files:
            store.resolve("secret:" + Path(name).stem)
    return manifest


def export_bundle(database: Path, destination: Path) -> Path:
    """Snapshot managed stores while holding exclusive runtime/catalog ownership."""
    database, destination = database.absolute(), destination.absolute()
    checked_path(database)
    checked_path(database.parent, directory=True)
    checked_path(destination, directory=True)
    with _lease(database), _lease(destination / ".backup-catalog"):
        identity = str(uuid.uuid4())
        stage = destination / (".orion-export-" + identity)
        create_private_directory(stage)
        # Failed exports deliberately remain private and unpublished for diagnosis.
        create_private_file(stage / "orion.db")
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(stage / "orion.db")) as target:
                source.backup(target)
        for folder in ("blobs", "provider-credentials"):
            create_private_directory(stage / folder)
            source_directory = database.parent / folder
            if not source_directory.exists() and not source_directory.is_symlink():
                continue
            checked_path(source_directory, directory=True)
            for source_path in sorted(source_directory.iterdir()):
                name = f"{folder}/{source_path.name}"
                if not _payload_name(name):
                    raise ValueError("Managed data directory contains an unexpected path")
                _copy(source_path, stage / name)
        files = {"orion.db": _fingerprint(stage / "orion.db")}
        for folder in ("blobs", "provider-credentials"):
            for path in sorted((stage / folder).iterdir()):
                files[f"{folder}/{path.name}"] = _fingerprint(path)
        schema, environment = _database_metadata(stage / "orion.db", set(files))
        manifest = {
            "format": "orion-managed-data",
            "version": 1,
            "id": identity,
            "created_at": datetime.now(UTC).isoformat(),
            "platform": sys.platform,
            "schema_sha256": schema,
            "environment_credentials": environment,
            "files": files,
        }
        # Validate protected records before publication without creating plaintext copies.
        credentials = ProtectedFileCredentialStore(stage / "provider-credentials")
        for reference in credentials.references():
            credentials.resolve(reference)
        encoded = _json_bytes(manifest)
        if (
            len(files) > MAX_FILES
            or len(encoded) > MANIFEST_LIMIT
            or sum(int(record["size"]) for record in files.values()) > MAX_TOTAL_BYTES
        ):
            raise ValueError("Backup inventory exceeds supported size")
        _write(stage / "manifest.json", encoded)
        with (stage / "orion.db").open("r+b") as snapshot:
            os.fsync(snapshot.fileno())
        published = destination / (_PREFIX + identity)
        stage.rename(published)
        return published


def import_bundle(bundle: Path, destination: Path) -> Path:
    """Restore into an absent data directory; never open/migrate a deployed DB."""
    bundle, destination = bundle.absolute(), destination.absolute()
    checked_path(destination.parent, directory=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Import requires a new data directory")
    with _lease(bundle.parent / ".backup-catalog"):
        manifest = validate_bundle(bundle)
        stage = destination.parent / (".orion-import-" + str(uuid.uuid4()))
        create_private_directory(stage)
        for folder in ("blobs", "provider-credentials"):
            create_private_directory(stage / folder)
        for name in manifest["files"]:
            _copy(bundle / name, stage / name)
            if _fingerprint(stage / name) != manifest["files"][name]:
                raise ValueError("Backup changed during restore")
        _database_metadata(stage / "orion.db", set(manifest["files"]))
        # A restored database is a new deployment. Revoke copied native owner
        # sessions/codes rather than resurrecting credentials from a snapshot.
        # Only the private staged copy is changed; the bundle stays immutable.
        with closing(sqlite3.connect(stage / "orion.db")) as restored:
            tables = {
                row[0]
                for row in restored.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            with restored:
                if "native_sessions" in tables:
                    restored.execute(
                        "UPDATE native_sessions SET revoked_at=COALESCE(revoked_at,?)",
                        (int(datetime.now(UTC).timestamp()),),
                    )
                if "native_enrollments" in tables:
                    restored.execute("DELETE FROM native_enrollments")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Import destination appeared during restore")
        stage.rename(destination)
    return destination / "orion.db"


def retain_bundles(directory: Path, *, keep: int) -> tuple[Path, ...]:
    """Prune only fully validated, privately owned bundles; preflight all first."""
    if type(keep) is not int or keep < 1:
        raise ValueError("Retention must keep at least one backup")
    directory = directory.absolute()
    checked_path(directory, directory=True)
    with _lease(directory / ".backup-catalog"):
        candidates = []
        for path in directory.iterdir():
            if path.name.startswith(_PREFIX):
                manifest = validate_bundle(path)
                candidates.append(
                    (datetime.fromisoformat(manifest["created_at"]), path.name, path, manifest)
                )
        candidates.sort(reverse=True)
        removed = []
        for _, _, path, manifest in candidates[keep:]:
            # Recheck immediately before destructive operations, including exact inventory.
            validate_bundle(path)
            for name in manifest["files"]:
                checked_path(path / name)
                (path / name).unlink()
            (path / "manifest.json").unlink()
            for folder in ("blobs", "provider-credentials"):
                child = path / folder
                if child.exists():
                    child.rmdir()
            path.rmdir()
            removed.append(path)
        return tuple(removed)
