"""Offline operator skill lifecycle; no server/model/MCP startup or script execution."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from orion.paths import database_path
from orion.persistence.ownership import RuntimeLease
from orion.persistence.sqlite import SQLiteStore
from orion.skills.packages import read_package
from orion.skills.service import SkillService


def run_skill_command(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="orion skill", description="Offline trusted skill catalog; stop Orion first"
    )
    commands = parser.add_subparsers(dest="operation", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--project")
    for name in ("install", "update"):
        command = commands.add_parser(name)
        if name == "update":
            command.add_argument("name")
        command.add_argument("directory", type=Path)
        command.add_argument("--source", choices=("user", "project"), default="user")
        command.add_argument("--project")
    for name in ("enable", "disable", "remove"):
        command = commands.add_parser(name)
        command.add_argument("name")
        command.add_argument("--source", choices=("bundled", "user", "project"), default="user")
        command.add_argument("--project")
    options = parser.parse_args(arguments)
    lease: RuntimeLease | None = None
    store: SQLiteStore | None = None
    try:
        path = database_path()
        lease = RuntimeLease(path)
        store = SQLiteStore(path, on_close=lease.close)
        service = SkillService(store)
        if options.operation == "list":
            result: dict[str, object] = {
                "skills": [
                    descriptor.model_dump(mode="json")
                    for descriptor in service.owner_catalog(project_id=options.project).values()
                ]
            }
        elif options.operation in {"install", "update"}:
            if options.operation == "update":
                package = read_package(options.directory, options.source, options.project)
                if package.descriptor.name != options.name:
                    raise ValueError("Skill update name mismatch")
                existing = service.owner_catalog(project_id=options.project).get(options.name)
                if existing is None or existing.source != options.source:
                    raise ValueError("Skill update is not installed")
            descriptor = service.install(
                options.directory, options.source, project_id=options.project
            )
            result = {"skill": descriptor.model_dump(mode="json")}
        elif options.operation == "remove":
            service.remove(options.name, options.source, project_id=options.project)
            result = {"removed": options.name}
        else:
            service.set_enabled(
                options.name,
                options.source,
                options.operation == "enable",
                project_id=options.project,
            )
            result = {"name": options.name, "enabled": options.operation == "enable"}
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        raise SystemExit(
            "Skill operation failed. Check package/scope and stop the active Orion runtime."
        ) from None
    finally:
        if store is not None:
            store.close()
        elif lease is not None:
            lease.close()
    print(json.dumps(result, ensure_ascii=True))
