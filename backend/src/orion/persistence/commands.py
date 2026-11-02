"""Command metadata only: no script, environment, cwd or output bytes in SQLite."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from orion.contracts import RuntimeScope
from orion.contracts.commands import CommandPage, CommandRunInput


class CommandPersistence:
    _connection: sqlite3.Connection
    _lock: threading.RLock

    def previous_command_call(self, request_id: str, call_id: str) -> bool:
        """Internal request/call lookup; scope/hash remain checked by create_command."""
        with self._lock:
            return (
                self._connection.execute(
                    "SELECT 1 FROM command_records WHERE request_id=? AND call_id=?",
                    (request_id, call_id),
                ).fetchone()
                is not None
            )

    def _create_command_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS command_records (
                    command_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    project_id TEXT, endpoint_id TEXT,
                    request_id TEXT REFERENCES requests(request_id) ON DELETE SET NULL,
                    call_id TEXT NOT NULL, target_ref TEXT NOT NULL, shell TEXT NOT NULL,
                    input_hash TEXT NOT NULL, max_output_bytes INTEGER NOT NULL,
                    state TEXT NOT NULL, observation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(request_id, call_id)
                );
                CREATE INDEX IF NOT EXISTS commands_owner ON command_records(session_id);
            """)

    def create_command(
        self,
        scope: RuntimeScope,
        values: CommandRunInput,
        request_id: str,
        call_id: str,
    ) -> tuple[dict[str, Any], bool]:
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM command_records WHERE request_id=? AND call_id=?",
                (request_id, call_id),
            ).fetchone()
            if existing:
                if (
                    existing["input_hash"] != values.payload_hash()
                    or existing["session_id"] != scope.session_id
                ):
                    raise PermissionError("Command call identity changed")
                return dict(existing), False
            identity = uuid.uuid4().hex
            now = datetime.now(UTC).isoformat()
            initial = CommandPage(
                command_id=identity,
                target_ref=values.target_ref,
                shell=values.shell,
                state="created",
                output_available=False,
            )
            self._connection.execute(
                "INSERT INTO command_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    scope.principal_id,
                    scope.workspace_id,
                    scope.session_id,
                    scope.project_id,
                    scope.endpoint_id,
                    request_id,
                    call_id,
                    values.target_ref,
                    values.shell,
                    values.payload_hash(),
                    values.max_output_bytes,
                    "created",
                    initial.model_dump_json(),
                    now,
                    now,
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM command_records WHERE command_id=?", (identity,)
            ).fetchone()
            assert row is not None
            return dict(row), True

    def command_record(self, scope: RuntimeScope, identity: str, target: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM command_records WHERE command_id=? AND target_ref=? "
                "AND session_id=? AND principal_id=? AND workspace_id=? "
                "AND project_id IS ? AND endpoint_id IS ?",
                (
                    identity,
                    target,
                    scope.session_id,
                    scope.principal_id,
                    scope.workspace_id,
                    scope.project_id,
                    scope.endpoint_id,
                ),
            ).fetchone()
        if row is None:
            raise PermissionError("Command is outside the current scope")
        return dict(row)

    def save_command_observation(self, page: CommandPage) -> None:
        safe = page.model_copy(update={"stdout": "", "stderr": "", "output_available": False})
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE command_records SET state=?, observation_json=?, updated_at=? "
                "WHERE command_id=? AND state IN ('created','running','outcome_unknown',?)",
                (
                    page.state,
                    safe.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                    page.command_id,
                    page.state,
                ),
            )

    def _recover_commands(self) -> None:
        # Called only inside the same transaction as request/authorization recovery.
        for row in self._connection.execute(
            "SELECT command_id,observation_json FROM command_records "
            "WHERE state IN ('created','running')"
        ).fetchall():
            previous = json.loads(row["observation_json"])
            previous.update(
                state="outcome_unknown",
                exit_code=None,
                process_tree_terminated=False,
                stdout="",
                stderr="",
                output_available=False,
            )
            self._connection.execute(
                "UPDATE command_records SET state='outcome_unknown', observation_json=?, "
                "updated_at=? WHERE command_id=?",
                (json.dumps(previous), datetime.now(UTC).isoformat(), row["command_id"]),
            )
