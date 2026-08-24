"""Small SQLite/WAL store for the first Orion vertical slice."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from orion.contracts import TimelineItem, TimelineKind


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteStore:
    """Persistence boundary; rows map to canonical public timeline semantics."""

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS model_configs (
                    model_config_id TEXT PRIMARY KEY,
                    provider_type TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    api_key TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS timeline (
                    item_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    request_id TEXT REFERENCES requests(request_id),
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    call_id TEXT,
                    tool_name TEXT
                );
                CREATE TABLE IF NOT EXISTS request_events (
                    event_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES requests(request_id),
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        self._connection.close()

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO sessions(session_id, created_at) VALUES (?, ?)",
                (session_id, _utc_now()),
            )
        return session_id

    def session_exists(self, session_id: str) -> bool:
        with self._lock:
            return (
                self._connection.execute(
                    "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                is not None
            )

    def create_request(self, session_id: str, status: str = "queued") -> str:
        request_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO requests(request_id, session_id, status, created_at) "
                "VALUES (?, ?, ?, ?)",
                (request_id, session_id, status, _utc_now()),
            )
        return request_id

    def start_request(self, request_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE requests SET status = ? WHERE request_id = ? AND status = ?",
                ("running", request_id, "queued"),
            )

    def complete_request(
        self, request_id: str, status: str, error_message: str | None = None
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE requests SET status = ?, error_message = ?, completed_at = ? "
                "WHERE request_id = ?",
                (status, error_message, _utc_now(), request_id),
            )

    def request(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT request_id, session_id, status, error_message, created_at, completed_at "
                "FROM requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def append_timeline(
        self,
        session_id: str,
        request_id: str,
        kind: str,
        payload: dict[str, Any],
        call_id: str | None = None,
        tool_name: str | None = None,
    ) -> TimelineItem:
        item = TimelineItem(
            item_id=str(uuid.uuid4()),
            session_id=session_id,
            created_at=datetime.now(UTC),
            kind=cast(TimelineKind, kind),
            payload=payload,
            call_id=call_id,
            tool_name=tool_name,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO timeline(item_id, session_id, request_id, created_at, kind,
                   payload_json, call_id, tool_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.item_id,
                    session_id,
                    request_id,
                    item.created_at.isoformat(),
                    kind,
                    json.dumps(payload),
                    call_id,
                    tool_name,
                ),
            )
        return item

    def timeline(self, session_id: str) -> list[TimelineItem]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT item_id, session_id, created_at, kind, payload_json, call_id, tool_name "
                "FROM timeline WHERE session_id = ? ORDER BY created_at, rowid",
                (session_id,),
            ).fetchall()
        return [
            TimelineItem(
                item_id=row["item_id"],
                session_id=row["session_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                kind=row["kind"],
                payload=json.loads(row["payload_json"]),
                call_id=row["call_id"],
                tool_name=row["tool_name"],
            )
            for row in rows
        ]

    def emit_event(self, request_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO request_events(event_id, request_id, created_at, event_type, "
                "payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), request_id, _utc_now(), event_type, json.dumps(payload)),
            )

    def events(self, request_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT event_type, payload_json, created_at FROM request_events "
                "WHERE request_id = ? ORDER BY created_at, rowid",
                (request_id,),
            ).fetchall()
        return [
            {
                "type": row["event_type"],
                "created_at": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def upsert_model_config(
        self, provider_type: str, base_url: str, model_id: str, api_key: str | None
    ) -> str:
        model_config_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute("UPDATE model_configs SET is_active = 0")
            self._connection.execute(
                """INSERT INTO model_configs(model_config_id, provider_type, base_url, model_id,
                   api_key, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (
                    model_config_id,
                    provider_type,
                    base_url.rstrip("/"),
                    model_id,
                    api_key,
                    _utc_now(),
                ),
            )
        return model_config_id

    def active_model_config(self) -> dict[str, str | None] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT model_config_id, provider_type, base_url, model_id, api_key "
                "FROM model_configs "
                "WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
