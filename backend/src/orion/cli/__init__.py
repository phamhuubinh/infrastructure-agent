"""Small local CLI surface."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import uvicorn

from orion.paths import database_path, log_path
from orion.security import redact_public


def main() -> None:
    parser = argparse.ArgumentParser(prog="orion")
    subcommands = parser.add_subparsers(dest="command", required=True)
    web = subcommands.add_parser("web", help="run Orion's local API")
    web.add_argument("--host", default=os.getenv("ORION_HOST", "127.0.0.1"))
    web.add_argument("--port", default=int(os.getenv("ORION_PORT", "61888")), type=int)
    web.add_argument("--data-dir", type=Path, help="persistent data directory")
    web.add_argument("--database", type=Path, help="SQLite database path")
    web.add_argument("--log-path", type=Path, help="sanitized application log path")
    log = subcommands.add_parser("log", help="show sanitized local Orion application logs")
    log.add_argument("--data-dir", type=Path, help="persistent data directory")
    log.add_argument("--database", type=Path, help="SQLite database path")
    log.add_argument("--log-path", type=Path, help="sanitized application log path")
    log.add_argument("--tail", type=int, default=100, help="number of records to show")
    arguments = parser.parse_args()
    if arguments.command == "web":
        _configure_paths(arguments)
        uvicorn.run(
            "orion.api.app:create_app", host=arguments.host, port=arguments.port, factory=True
        )
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
