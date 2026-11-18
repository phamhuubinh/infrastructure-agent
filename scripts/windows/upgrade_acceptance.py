"""Read-only checks before first launch after a maintenance-window installation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path

from upgrade_readiness import database_state, inventory, sha, verify


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    args = parser.parse_args()
    backup = args.backup.absolute()
    payload = args.payload.absolute()
    local = Path(os.environ["LOCALAPPDATA"])
    verify(backup)
    expected = inventory(payload / "backend")
    for name, digest in expected.items():
        if sha(local / "Orion/backend" / name) != digest:
            raise ValueError("Installed backend differs from candidate")
    for name, digest in inventory(payload / "web").items():
        if sha(local / "Orion/web" / name) != digest:
            raise ValueError("Installed Web differs from candidate")
    for name in ("Orion.exe", "WebView2Loader.dll"):
        if sha(local / "Orion" / name) != sha(payload / name):
            raise ValueError("Installed native application differs from candidate")
    # Read SQLite with WAL awareness. Never initialize/migrate the deployed DB.
    import sqlite3
    from contextlib import closing

    database = local / "io.orion.desktop/managed/orion.db"
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    with closing(
        sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    ) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Installed database integrity failed")
        if database_state(connection) != manifest["database_tables"]:
            raise ValueError("Database changed since the maintenance snapshot")
    managed = local / "io.orion.desktop/managed"
    for folder in ("provider-credentials", "blobs"):
        if inventory(managed / folder) != inventory(backup / "managed" / folder):
            raise ValueError("Managed payloads changed during upgrade")
    # Export only to a temporary sibling inside the protected backup directory.
    with tempfile.TemporaryDirectory(prefix="check-host-", dir=backup) as temporary:
        target = Path(temporary) / "desktop-host.reg"
        subprocess.run(
            [
                "reg.exe",
                "export",
                r"HKCU\Software\Orion\DesktopHost",
                str(target),
                "/y",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if sha(target) != sha(backup / "desktop-host.reg"):
            raise ValueError("Host configuration changed")
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            run = list(winreg.QueryValueEx(key, "OrionDesktopHost"))
    except FileNotFoundError:
        run = None
    if run != json.loads((backup / "autostart.json").read_text(encoding="utf-8")):
        raise ValueError("Host autostart changed")
    tailscale = Path(os.environ["ProgramFiles"]) / "Tailscale/tailscale.exe"
    serve = json.loads(
        subprocess.check_output([str(tailscale), "serve", "status", "--json"])
    )
    if serve != json.loads((backup / "tailscale-serve.json").read_bytes()):
        raise ValueError("Tailscale Serve changed")
    if any(serve.get("AllowFunnel", {}).values()):
        raise ValueError("Funnel is enabled")
    print(
        "PASS installed payload, SQLite rows, credential files, Host settings and Serve"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - never display protected values
        print(f"FAIL upgrade acceptance ({type(error).__name__})", file=sys.stderr)
        sys.exit(1)
