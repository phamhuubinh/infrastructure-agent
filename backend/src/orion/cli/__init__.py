"""The intentionally small public CLI for the local Orion web application."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import uvicorn

from orion.paths import (
    ORION_HEALTH_IDENTITY,
    ORION_HOST,
    ORION_PORT,
    PACKAGED_UI_SHELL,
    database_path,
    log_path,
    packaged_ui_directory,
)
from orion.security import redact_public

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
    _invalid_command(command)


def _show_help() -> None:
    print(
        "Orion\n\nUsage:\n"
        "  orion          Start Orion\n"
        "  orion web      Start Orion\n"
        "  orion log      Show Orion logs\n"
        "  orion help     Show this help"
    )


def _invalid_command(command: list[str]) -> None:
    entered = " ".join(command) or "(none)"
    raise SystemExit(f"Unknown Orion command: {entered}\nRun 'orion help' for help.")


def _configure_default_log_path() -> None:
    # Environment-owned paths remain useful for isolated automation, without
    # becoming public CLI configuration or changing normal user defaults.
    if "ORION_LOG_PATH" not in os.environ:
        os.environ["ORION_LOG_PATH"] = str(log_path())


def _run_web() -> None:
    frontend = packaged_ui_directory()
    if not (frontend / PACKAGED_UI_SHELL).is_file():
        raise SystemExit(
            f"Orion's packaged UI is missing at {frontend}. Run ./install.sh to build it."
        )
    if _orion_is_healthy():
        print(f"Orion is already running at {ORION_URL}")
        _open_desktop_url(ORION_URL)
        return
    if _port_is_occupied():
        raise SystemExit("Port 61888 is already in use by another application.")

    config = uvicorn.Config(
        "orion.api.app:create_app",
        host=ORION_HOST,
        port=ORION_PORT,
        factory=True,
    )
    server = uvicorn.Server(config)
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
