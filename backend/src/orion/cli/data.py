"""Offline data lifecycle commands; no server, model or tool startup."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from orion.paths import database_path
from orion.persistence.backup import export_bundle, import_bundle, retain_bundles


def run_data_command(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="orion data")
    commands = parser.add_subparsers(dest="operation", required=True)
    export = commands.add_parser("export", help="Stop Orion before exporting managed data")
    export.add_argument("directory", type=Path)
    restore = commands.add_parser("import", help="Restore trusted data into a new directory")
    restore.add_argument("bundle", type=Path)
    restore.add_argument("directory", type=Path)
    retain = commands.add_parser("retain", help="Delete only validated managed-data backups")
    retain.add_argument("directory", type=Path)
    retain.add_argument("--keep", type=int, required=True)
    options = parser.parse_args(arguments)
    result: dict[str, str | list[str]]
    try:
        if options.operation == "export":
            result = {"bundle": str(export_bundle(database_path(), options.directory))}
        elif options.operation == "import":
            result = {"database": str(import_bundle(options.bundle, options.directory))}
        else:
            result = {
                "removed": [
                    str(path) for path in retain_bundles(options.directory, keep=options.keep)
                ]
            }
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        # Never print raw SQLite rows, credential contents or hostile manifest strings.
        raise SystemExit(
            "Data operation failed. Check paths, bundle integrity and stop Orion."
        ) from None
    print(json.dumps(result))
