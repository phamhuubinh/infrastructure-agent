"""Small local CLI surface."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from orion.paths import database_path, log_path, packaged_ui_directory
from orion.security import redact_public


def main() -> None:
    parser = argparse.ArgumentParser(prog="orion")
    subcommands = parser.add_subparsers(dest="command")
    web = subcommands.add_parser("web", help="run Orion's local web application")
    web.add_argument("--host", default=os.getenv("ORION_HOST", "127.0.0.1"))
    web.add_argument("--port", default=int(os.getenv("ORION_PORT", "61888")), type=int)
    web.add_argument("--data-dir", type=Path, help="persistent data directory")
    web.add_argument("--database", type=Path, help="SQLite database path")
    web.add_argument("--log-path", type=Path, help="sanitized application log path")
    web.add_argument("--no-open", action="store_true", help="do not open a browser")
    log = subcommands.add_parser("log", help="show sanitized local Orion application logs")
    log.add_argument("--data-dir", type=Path, help="persistent data directory")
    log.add_argument("--database", type=Path, help="SQLite database path")
    log.add_argument("--log-path", type=Path, help="sanitized application log path")
    log.add_argument("--tail", type=int, default=100, help="number of records to show")
    arguments = parser.parse_args()
    if arguments.command is None:
        arguments.command = "web"
        arguments.host = os.getenv("ORION_HOST", "127.0.0.1")
        arguments.port = int(os.getenv("ORION_PORT", "61888"))
        arguments.data_dir = None
        arguments.database = None
        arguments.log_path = None
        arguments.no_open = False
    if arguments.command == "web":
        _configure_paths(arguments)
        _run_web(arguments)
    else:
        _configure_paths(arguments)
        _show_log(log_path(), database_path(), arguments.tail)


def _configure_paths(arguments: argparse.Namespace) -> None:
    if arguments.data_dir is not None:
        os.environ["ORION_DATA_DIR"] = str(arguments.data_dir.expanduser())
    if arguments.database is not None:
        os.environ["ORION_DATABASE_PATH"] = str(arguments.database.expanduser())
    if arguments.log_path is not None:
        os.environ["ORION_LOG_PATH"] = str(arguments.log_path.expanduser())
    elif "ORION_LOG_PATH" not in os.environ:
        os.environ["ORION_LOG_PATH"] = str(log_path())


def _run_web(arguments: argparse.Namespace) -> None:
    frontend = packaged_ui_directory()
    if not (frontend / "index.html").is_file():
        raise SystemExit(
            f"Orion's packaged UI is missing at {frontend}. Run ./install.sh to build it."
        )
    config = uvicorn.Config(
        "orion.api.app:create_app",
        host=arguments.host,
        port=arguments.port,
        factory=True,
    )
    server = uvicorn.Server(config)
    if not arguments.no_open and _is_loopback_host(arguments.host):
        url = _local_url(arguments.host, arguments.port)
        threading.Thread(
            target=_open_browser_when_ready, args=(server, url), daemon=True, name="orion-browser"
        ).start()
    server.run()


def _is_loopback_host(host: str) -> bool:
    return host.lower() in {"127.0.0.1", "localhost", "::1"}


def _local_url(host: str, port: int) -> str:
    return f"http://[{host}]:{port}/" if ":" in host else f"http://{host}:{port}/"


def _open_browser_when_ready(server: uvicorn.Server, url: str) -> None:
    while not server.started and not server.should_exit:
        time.sleep(0.05)
    if server.started and not server.should_exit:
        webbrowser.open(url)


def _show_log(log_file: Path, database: Path, tail: int) -> None:
    if tail < 1:
        raise SystemExit("--tail must be at least 1")
    print(f"database: {database.resolve()}")
    print(f"log: {log_file.resolve()}")
    if not log_file.exists():
        print("No application log records yet.")
        return
    lines = log_file.read_text(encoding="utf-8").splitlines()[-tail:]
    for line in lines:
        try:
            print(json.dumps(redact_public(json.loads(line)), sort_keys=True))
        except json.JSONDecodeError:
            print("[invalid redacted log record]")


if __name__ == "__main__":
    main()
