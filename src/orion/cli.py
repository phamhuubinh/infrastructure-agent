"""Small local CLI surface for the M1 app."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="orion")
    subcommands = parser.add_subparsers(dest="command", required=True)
    web = subcommands.add_parser("web", help="run Orion's local API")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", default=61888, type=int)
    log = subcommands.add_parser("log", help="show the local database location")
    log.add_argument("--database", default="data/orion.db")
    arguments = parser.parse_args()
    if arguments.command == "web":
        uvicorn.run(
            "orion.api.app:create_app", host=arguments.host, port=arguments.port, factory=True
        )
    else:
        print(Path(arguments.database).resolve())
