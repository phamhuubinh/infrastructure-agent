"""The intentionally small public CLI for the local Orion web application."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import uvicorn

from orion.access.remote import RemoteAccessConfig, hash_password
from orion.paths import (
    ORION_HEALTH_IDENTITY,
    ORION_HOST,
    ORION_PORT,
    PACKAGED_UI_SHELL,
    database_path,
    log_path,
    packaged_ui_directory,
    source_checkout_root,
)
from orion.security import redact_public
from orion.ui_package import build_and_package_ui

ORION_URL = f"http://{ORION_HOST}:{ORION_PORT}/"


def main() -> None:
    """Run one of Orion's four public commands without exposing dev switches."""
    command = sys.argv[1:]
    if command in ([], ["web"]):
        _configure_default_log_path()
        _run_web()
        return
    if command == ["log"]:
        _configure_default_log_path()
        _show_log(log_path(), database_path())
        return
    if command == ["help"]:
        _show_help()
        return
    if command == ["auth", "hash-password"]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Password: ")
                confirmation = getpass.getpass("Confirm password: ")
        except getpass.GetPassWarning:
            raise SystemExit("A terminal that hides password input is required.") from None
        if password != confirmation:
            raise SystemExit("Passwords do not match.")
        try:
            print(hash_password(password))
        except ValueError as error:
            raise SystemExit(str(error)) from error
        return
    if command == ["model", "status", "embeddings"]:
        from orion.knowledge.local_embeddings import model_directory, model_status

        print(f"embeddings: {model_status()} ({model_directory()})")
        return
    if command == ["model", "install", "embeddings"]:
        from orion.knowledge.local_embeddings import install_model, model_directory

        try:
            print(f"embeddings: {install_model()} ({model_directory()})")
        except RuntimeError as error:
            raise SystemExit(str(error)) from error
        return
    if command[:2] == ["knowledge", "semantic-index"]:
        _semantic_backfill(command[2:])
        return
    _invalid_command(command)


def _show_help() -> None:
    print(
        "Orion\n\nUsage:\n"
        "  orion          Start Orion\n"
        "  orion web      Start Orion\n"
        "  orion log      Show Orion logs\n"
        "  orion auth hash-password  Generate an encoded Argon2id hash\n"
        "  orion model status embeddings   Show local E5 model status\n"
        "  orion model install embeddings  Provision pinned local E5 model\n"
        "  orion knowledge semantic-index [--max-documents N]  Inspect up to N ready documents\n"
        "  orion help     Show this help"
    )


def _semantic_backfill(arguments: list[str]) -> None:
    if not arguments:
        max_documents = 100
    elif len(arguments) == 2 and arguments[0] == "--max-documents":
        try:
            max_documents = int(arguments[1])
        except ValueError as error:
            raise SystemExit("--max-documents must be a positive integer") from error
    else:
        _invalid_command(["knowledge", "semantic-index", *arguments])
        return
    if max_documents <= 0:
        raise SystemExit("--max-documents must be a positive integer")
    from orion.knowledge.local_embeddings import LocalE5Embeddings
    from orion.knowledge.semantic import SemanticIndexService
    from orion.persistence.sqlite import SQLiteStore

    try:
        embeddings = LocalE5Embeddings()
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    store = SQLiteStore(database_path())
    try:
        progress = SemanticIndexService(store, embeddings).reconcile_missing(
            max_documents=max_documents
        )
        print(
            "semantic indexing: "
            f"inspected={progress.inspected} reindexed={progress.reindexed} "
            f"failed={progress.failed} wrapped={progress.wrapped} "
            f"cursor={progress.cursor_document_id or 'none'}"
        )
    finally:
        store.close()


def _invalid_command(command: list[str]) -> None:
    entered = " ".join(command) or "(none)"
    raise SystemExit(f"Unknown Orion command: {entered}\nRun 'orion help' for help.")


def _configure_default_log_path() -> None:
    # Environment-owned paths remain useful for isolated automation, without
    # becoming public CLI configuration or changing normal user defaults.
    if "ORION_LOG_PATH" not in os.environ:
        os.environ["ORION_LOG_PATH"] = str(log_path())


def _run_web() -> None:
    try:
        remote = RemoteAccessConfig.from_environment()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    frontend = packaged_ui_directory()
    checkout = source_checkout_root()
    if checkout is not None and frontend.resolve() == (checkout / ".orion-ui").resolve():
        try:
            build_and_package_ui(checkout, frontend)
        except RuntimeError as error:
            raise SystemExit(str(error)) from error
    if not (frontend / PACKAGED_UI_SHELL).is_file():
        raise SystemExit(
            f"Orion's packaged UI is missing at {frontend}. Run ./install.sh to build it."
        )
    if not remote.enabled and _orion_is_healthy():
        print(f"Orion is already running at {ORION_URL}")
        _open_desktop_url(ORION_URL)
        return
    if _port_is_occupied():
        raise SystemExit("Port 61888 is already in use by another application.")

    config = uvicorn.Config(
        "orion.api.app:create_app",
        host=remote.bind_host,
        port=ORION_PORT,
        factory=True,
        proxy_headers=False,
    )
    server = uvicorn.Server(config)
    if remote.enabled:
        print(f"Remote Orion origin: {remote.public_origin}")
    else:
        threading.Thread(
            target=_open_when_healthy,
            args=(server,),
            daemon=True,
            name="orion-url-opener",
        ).start()
    try:
        server.run()
    except KeyboardInterrupt:
        # Uvicorn re-raises its captured interactive SIGINT after it has
        # completed graceful shutdown. Its own CLI catches this at the outer
        # boundary; Orion owns that boundary when calling Server.run directly.
        return


def _orion_is_healthy() -> bool:
    try:
        with urlopen(f"{ORION_URL}api/health", timeout=0.5) as response:  # noqa: S310 - fixed loopback URL.
            payload = json.loads(response.read())
            return (
                response.status == 200
                and isinstance(payload, dict)
                and payload.get("status") == "ok"
                and payload.get("identity") == ORION_HEALTH_IDENTITY
            )
    except (OSError, TimeoutError, HTTPError, URLError, json.JSONDecodeError):
        return False


def _port_is_occupied() -> bool:
    try:
        with socket.create_connection((ORION_HOST, ORION_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _open_when_healthy(server: uvicorn.Server) -> None:
    while not server.should_exit:
        if _orion_is_healthy():
            _open_desktop_url(ORION_URL)
            return
        time.sleep(0.05)


def _open_desktop_url(url: str) -> None:
    """Ask the OS to open a URL; an unavailable desktop never stops Orion."""
    print(f"Open Orion at {url}")
    if sys.platform == "darwin":
        command = ["open", url]
    elif sys.platform.startswith("win"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]  # noqa: S606 - URL association.
        except OSError:
            pass
        return
    else:
        opener = shutil.which("xdg-open") or shutil.which("gio")
        if opener is None:
            return
        command = [opener, url] if Path(opener).name == "xdg-open" else [opener, "open", url]
    try:
        subprocess.run(  # noqa: S603 - fixed argv for the system URL opener.
            command,
            check=False,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _show_log(log_file: Path, database: Path) -> None:
    print(f"database: {database.resolve()}")
    print(f"log: {log_file.resolve()}")
    if not log_file.exists():
        print("No application log records yet.")
        return
    for line in log_file.read_text(encoding="utf-8").splitlines()[-100:]:
        try:
            print(json.dumps(redact_public(json.loads(line)), sort_keys=True))
        except json.JSONDecodeError:
            print("[invalid redacted log record]")


if __name__ == "__main__":
    main()
