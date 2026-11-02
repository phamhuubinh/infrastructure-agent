"""Durable client admission keys bind one actual scope/content to one server request."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from orion.contracts import RuntimeScope


class RequestAdmissionPersistence:
    _connection: sqlite3.Connection
    _lock: threading.RLock

    def _create_admission_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS request_admissions (
                    principal_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    client_request_id TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    request_id TEXT NOT NULL UNIQUE
                        REFERENCES requests(request_id) ON DELETE CASCADE,
                    input_hash TEXT NOT NULL,
                    PRIMARY KEY(principal_id,workspace_id,client_request_id)
                )
            """)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS request_events_request ON request_events(request_id)"
            )

    def request_admission(self, principal: str, workspace: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT session_id,request_id,input_hash FROM request_admissions "
                "WHERE principal_id=? AND workspace_id=? AND client_request_id=?",
                (principal, workspace, key),
            ).fetchone()
        return dict(row) if row else None

    def admit_request(
        self,
        scope: RuntimeScope,
        key: str,
        digest: str,
        *,
        initial_status: Literal["queued", "cancelled"] = "queued",
    ) -> tuple[str, bool]:
        def previous() -> str | None:
            row = self.request_admission(scope.principal_id, scope.workspace_id, key)
            if row is None:
                return None
            if row["session_id"] != scope.session_id or row["input_hash"] != digest:
                raise PermissionError("Client admission identity changed")
            return str(row["request_id"])

        with self._lock:
            existing = previous()
            if existing is not None:
                return existing, False
            request = str(uuid.uuid4())
            try:
                with self._connection:
                    now = datetime.now(UTC).isoformat()
                    self._connection.execute(
                        "INSERT INTO requests"
                        "(request_id,session_id,status,created_at,completed_at) "
                        "VALUES (?,?,?,?,?)",
                        (
                            request,
                            scope.session_id,
                            initial_status,
                            now,
                            now if initial_status == "cancelled" else None,
                        ),
                    )
                    self._connection.execute(
                        "INSERT INTO request_admissions VALUES (?,?,?,?,?,?)",
                        (
                            scope.principal_id,
                            scope.workspace_id,
                            key,
                            scope.session_id,
                            request,
                            digest,
                        ),
                    )
            except sqlite3.IntegrityError:
                # A separate writer can win the unique key after our first read.
                # The failed transaction also rolls back its orphan request row.
                existing = previous()
                if existing is None:
                    raise
                return existing, False
        return request, True

    def is_admitted_request(self, session_id: str, request_id: str) -> bool:
        with self._lock:
            return (
                self._connection.execute(
                    "SELECT 1 FROM request_admissions WHERE session_id=? AND request_id=?",
                    (session_id, request_id),
                ).fetchone()
                is not None
            )

    def request_event_page(
        self,
        request_id: str,
        after: str | None,
        limit: int = 64,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not 1 <= limit <= 256:
            raise ValueError("Invalid event page limit")
        result: list[dict[str, Any]] = []
        total = 0
        with self._lock:
            boundary = 0
            if after is not None:
                cursor = self._connection.execute(
                    "SELECT rowid FROM request_events WHERE request_id=? AND event_id=?",
                    (request_id, after),
                ).fetchone()
                if cursor is None:
                    raise ValueError("Event cursor is unavailable")
                boundary = cursor[0]
            rows = self._connection.execute(
                "SELECT event_id,event_type,created_at,"
                "length(CAST(payload_json AS BLOB)) AS bytes,"
                "substr(CAST(payload_json AS BLOB),1,1048577) AS payload "
                "FROM request_events WHERE request_id=? AND rowid>? ORDER BY rowid LIMIT ?",
                (request_id, boundary, limit + 1),
            )
            for row in rows:
                if len(result) >= limit or (result and total + row["bytes"] > 2_097_152):
                    return result, True
                if row["bytes"] > 1_048_576:
                    raise ValueError("Event exceeds the transport bound")
                result.append(
                    {
                        "event_id": row["event_id"],
                        "type": row["event_type"],
                        "created_at": row["created_at"],
                        "payload": json.loads(row["payload"]),
                    }
                )
                total += row["bytes"]
        return result, False
