"""Synthetic SQLite, DPAPI and Owner state for a disposable release runner."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from orion.access.owner import OwnerAuth, totp_code
from orion.cli.upgrade_snapshot import check_database, inventory, verify
from orion.endpoints.persistence import EndpointStore
from orion.models.credential_store import ProtectedFileCredentialStore
from orion.persistence.sqlite import SQLiteStore
from pydantic import SecretStr


def seed_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    store = SQLiteStore(root / "orion.db")
    try:
        # The baseline represents an already-run installation of this same
        # build. Composition initializes endpoint storage even in Client mode.
        EndpointStore(store)
        owner = OwnerAuth(store)
        setup, uri = owner.start_setup(secrets.token_urlsafe(24))
        encoded = parse_qs(urlsplit(uri).query)["secret"][0]
        secret = base64.b32decode(encoded + "=" * (-len(encoded) % 8))
        owner.confirm_setup(
            setup, totp_code(secret, int(time.time() // 30)), rotation=False
        )
        project = store.create_project("Update fixture")
        session_id = store.create_session(project_id=project["project_id"])
        store.append_timeline(
            session_id, None, "user_message", {"content": "Preserve fixture"}
        )
        reference = ProtectedFileCredentialStore(root / "provider-credentials").put(
            SecretStr(secrets.token_urlsafe(24))
        )
        store.create_model_config(
            "openai_compatible",
            "http://127.0.0.1:1/v1",
            "update-fixture",
            None,
            credential_ref=reference,
        )
    finally:
        store.close()


def verify_fixture(root: Path, snapshot: Path) -> None:
    verify(snapshot)
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    before = manifest["database_tables"]
    after = check_database(root / "orion.db")
    if before != after:
        added = sorted(after.keys() - before.keys())
        removed = sorted(before.keys() - after.keys())
        changed = sorted(
            key for key in before.keys() & after.keys() if before[key] != after[key]
        )
        raise RuntimeError(
            f"Installed update changed the fixture database: added={added}, "
            f"removed={removed}, changed={changed}"
        )
    for folder in ("provider-credentials", "blobs"):
        if inventory(root / folder) != inventory(snapshot / "managed" / folder):
            raise RuntimeError(f"The fixture {folder} files changed")


def verify_host_settings(snapshot: Path) -> None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            autostart = list(winreg.QueryValueEx(key, "OrionDesktopHost"))
    except FileNotFoundError:
        autostart = None
    if autostart != json.loads(
        (snapshot / "autostart.json").read_text(encoding="utf-8")
    ):
        raise RuntimeError("The fixture Host autostart settings changed")

    registry_key = r"Software\Orion\DesktopHost"
    expected = snapshot / "desktop-host.reg"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_key):
            present = True
    except FileNotFoundError:
        present = False
    if present != expected.is_file():
        raise RuntimeError("The fixture Host configuration presence changed")
    if present:
        with tempfile.TemporaryDirectory(prefix="orion-update-settings-") as temp:
            exported = Path(temp) / "desktop-host.reg"
            subprocess.run(
                ["reg.exe", "export", f"HKCU\\{registry_key}", str(exported)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if exported.read_bytes() != expected.read_bytes():
                raise RuntimeError("The fixture Host configuration changed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-receipt", type=Path)
    args = parser.parse_args()
    if os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("Synthetic release fixture requires a disposable runner.")
    root = Path(os.environ["LOCALAPPDATA"]) / "io.orion.desktop/managed"
    if args.verify_receipt:
        receipt = json.loads(args.verify_receipt.read_text(encoding="utf-8"))
        snapshot = Path(receipt["snapshot"])
        verify_fixture(root, snapshot)
        verify_host_settings(snapshot)
    else:
        seed_fixture(root)


if __name__ == "__main__":
    main()
