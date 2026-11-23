"""Create and verify a private online snapshot without stopping the deployed Host.

Run with the repository backend on PYTHONPATH. This command never installs,
restores over deployed files, authenticates Owner, or changes Tailscale settings.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

from orion.models.credential_store import ProtectedFileCredentialStore
from orion.persistence.sqlite import SQLiteStore


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(directory: Path) -> dict[str, str]:
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Backup does not follow linked paths")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = sha(path)
    return result


def copy_checked(source: Path, destination: Path) -> None:
    before = inventory(source)
    shutil.copytree(source, destination)
    if before != inventory(source) or before != inventory(destination):
        raise ValueError("Files changed during backup; create another snapshot")


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    identity = subprocess.check_output(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"], text=True
    ).strip()
    sid = next(csv.reader([identity]))[1]
    if not sid.startswith("S-1-"):
        raise ValueError("Cannot determine account SID")
    subprocess.run(
        [
            "icacls.exe",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"*{sid}:(OI)(CI)F",
            "*S-1-5-18:(OI)(CI)F",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def database_state(connection: sqlite3.Connection) -> dict[str, str]:
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    result = {}
    for (name,) in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        rows = connection.execute(f"SELECT * FROM {quoted}").fetchall()
        encoded = sorted(
            json.dumps(row, default=lambda value: {"bytes": value.hex()}, ensure_ascii=False)
            for row in rows
        )
        result[name] = hashlib.sha256("\n".join(encoded).encode()).hexdigest()
    return result


def check_database(path: Path) -> dict[str, str]:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign key check failed")
        owner = db.execute(
            "SELECT password_hash,totp_secret,recovery_digests FROM desktop_owner WHERE id=1"
        ).fetchone()
        if owner is None or not all(owner):
            raise ValueError("Owner security state is missing")
        for (blob,) in db.execute("SELECT blob_id FROM documents WHERE deleted_at IS NULL"):
            if not (path.parent / "blobs" / blob).is_file():
                raise ValueError("Snapshot is missing a document blob")
        credentials = ProtectedFileCredentialStore(path.parent / "provider-credentials")
        refs = set(credentials.references())
        for reference in refs:
            credentials.resolve(reference)
        for (reference,) in db.execute("SELECT credential_ref FROM model_configs"):
            if reference and reference.startswith("secret:") and reference not in refs:
                raise ValueError("Snapshot is missing a model credential")
        return database_state(db)


def verify(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        if sha(directory / name) != digest:
            raise ValueError("Backup checksum mismatch")
    if check_database(directory / "managed/orion.db") != manifest["database_tables"]:
        raise ValueError("Backup table contents differ")


def snapshot(
    destination: Path, *, online_only: bool = False, installation: Path | None = None
) -> Path:
    if sys.platform != "win32":
        raise OSError("A managed upgrade snapshot requires Windows")
    import winreg

    local = Path(os.environ["LOCALAPPDATA"])
    managed = local / "io.orion.desktop/managed"
    root = destination / ("before-upgrade-8eb4ad2-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    private_directory(root)
    copied = root / "managed"
    copied.mkdir()
    # Copy append-only payloads first, then take a WAL-consistent SQLite snapshot.
    before = {}
    for folder in ("provider-credentials", "blobs"):
        before[folder] = inventory(managed / folder)
        copy_checked(managed / folder, copied / folder)
    with closing(sqlite3.connect((managed / "orion.db").as_uri() + "?mode=ro", uri=True)) as src:
        src.execute("BEGIN")
        state = database_state(src)
        with closing(sqlite3.connect(copied / "orion.db")) as target:
            src.backup(target)
        src.rollback()
    for folder, hashes in before.items():
        if inventory(managed / folder) != hashes:
            raise ValueError("Managed payloads changed during snapshot; retry")
    if check_database(copied / "orion.db") != state:
        raise ValueError("Snapshot differs from source read transaction")
    copy_checked(installation or local / "Orion", root / "installed")
    for key, filename in (
        (r"HKCU\Software\Orion\DesktopHost", "desktop-host.reg"),
        (
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Orion",
            "uninstall.reg",
        ),
    ):
        result = subprocess.run(
            ["reg.exe", "export", key, str(root / filename), "/y"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode and filename == "desktop-host.reg":
            raise ValueError("Cannot back up Host configuration")
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as registry_key:
            autostart = winreg.QueryValueEx(registry_key, "OrionDesktopHost")
    except FileNotFoundError:
        autostart = None
    (root / "autostart.json").write_text(json.dumps(autostart), encoding="utf-8")
    tailscale = Path(os.environ["ProgramFiles"]) / "Tailscale/tailscale.exe"
    serve = subprocess.check_output([str(tailscale), "serve", "status", "--json"])
    if not online_only and any(json.loads(serve).get("AllowFunnel", {}).values()):
        raise ValueError("Funnel is enabled")
    (root / "tailscale-serve.json").write_bytes(serve)
    # Exercise a byte-for-byte rollback into a new directory, then run only DB
    # initialization. No listener, model request, Owner verification or TOTP runs.
    copy_checked(copied, root / "rollback-drill")
    store = SQLiteStore(root / "rollback-drill/orion.db")
    store.close()
    if check_database(root / "rollback-drill/orion.db") != state:
        raise ValueError("Rollback initialization changed table contents")
    original = ProtectedFileCredentialStore(managed / "provider-credentials")
    restored = ProtectedFileCredentialStore(root / "rollback-drill/provider-credentials")
    for reference in restored.references():
        if not hmac.compare_digest(
            original.resolve(reference).get_secret_value(),
            restored.resolve(reference).get_secret_value(),
        ):
            raise ValueError("Restored DPAPI credential differs")
    files = inventory(root)
    manifest = {
        "format": "orion-live-upgrade-snapshot-v1",
        "database_tables": state,
        "files": files,
        "rollback_drill": "PASS",
        "maintenance_snapshot_required": True,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    verify(root)
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", type=Path, metavar="BACKUP_PARENT")
    mode.add_argument("--verify", type=Path, metavar="BACKUP")
    parser.add_argument(
        "--online-only",
        action="store_true",
        help="For a backup outside maintenance, record the live Serve/Funnel state as-is",
    )
    args = parser.parse_args()
    if args.online_only and not args.snapshot:
        parser.error("--online-only requires --snapshot")
    if args.snapshot:
        path = snapshot(args.snapshot.absolute(), online_only=args.online_only)
        print(f"PASS private snapshot and isolated rollback drill: {path}")
    else:
        verify(args.verify.absolute())
        print("PASS backup hashes, SQLite, history, Owner state and DPAPI availability")


def guarded_main() -> None:
    try:
        main()
    except Exception as error:  # noqa: BLE001 - suppress secret-bearing exception payloads
        # Operational failures must never dump user rows, credential payloads or settings.
        print(
            f"FAIL upgrade readiness ({type(error).__name__}); backup remains private",
            file=sys.stderr,
        )
        sys.exit(1)


def snapshot_for_update(installation: str) -> None:
    """Called by the frozen sidecar in the native update handoff, after clean shutdown."""
    try:
        directory = Path(installation)
        if not directory.is_absolute() or not (directory / "Orion.exe").is_file():
            raise ValueError("Invalid installed application directory")
        snapshot(
            Path(os.environ["LOCALAPPDATA"]) / "OrionRecovery",
            online_only=True,
            installation=directory,
        )
    except Exception:  # operational errors must not print data or credentials
        raise SystemExit("The Orion update snapshot could not be verified.") from None
