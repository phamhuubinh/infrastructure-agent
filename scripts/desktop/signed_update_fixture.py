"""Synthetic SQLite, DPAPI and Owner state for a disposable release runner."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from orion.access.owner import OwnerAuth, totp_code
from orion.cli.upgrade_snapshot import check_database, inventory, verify
from orion.models.credential_store import ProtectedFileCredentialStore
from orion.persistence.sqlite import SQLiteStore
from pydantic import SecretStr


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
        verify(snapshot)
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        if check_database(root / "orion.db") != manifest["database_tables"]:
            raise RuntimeError("Installed update changed the fixture database")
        if inventory(root / "provider-credentials") != inventory(
            snapshot / "managed/provider-credentials"
        ):
            raise RuntimeError("The fixture DPAPI files changed")
        return
    root.mkdir(parents=True, exist_ok=False)
    store = SQLiteStore(root / "orion.db")
    try:
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
        ProtectedFileCredentialStore(root / "provider-credentials").put(
            SecretStr(secrets.token_urlsafe(24))
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
