"""SQLite/WAL persistence boundary."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from orion.contracts import TimelineItem, TimelineKind

MAX_SESSION_SUMMARIES = 100


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
                    principal_id TEXT NOT NULL DEFAULT 'local',
                    workspace_id TEXT NOT NULL DEFAULT 'local',
                    project_id TEXT REFERENCES projects(project_id),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    instructions TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    attachment_id TEXT NOT NULL UNIQUE,
                    session_id TEXT REFERENCES sessions(session_id),
                    project_id TEXT REFERENCES projects(project_id),
                    blob_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    media_type TEXT,
                    status TEXT NOT NULL,
                    normalized_text TEXT,
                    error_message TEXT,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (
                        (session_id IS NOT NULL AND project_id IS NULL)
                        OR (session_id IS NULL AND project_id IS NOT NULL)
                    )
                );
                CREATE INDEX IF NOT EXISTS documents_session_visibility
                    ON documents(session_id, status, deleted_at);
                CREATE TABLE IF NOT EXISTS document_segments (
                    segment_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    page INTEGER,
                    section TEXT,
                    UNIQUE(document_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS document_segments_document
                    ON document_segments(document_id, ordinal);
                CREATE TABLE IF NOT EXISTS document_ingestion_events (
                    event_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    state TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"] for row in self._connection.execute("PRAGMA table_info(sessions)")
            }
            if "principal_id" not in columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN principal_id TEXT NOT NULL DEFAULT 'local'"
                )
            if "workspace_id" not in columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'local'"
                )
            if "project_id" not in columns:
                self._connection.execute("ALTER TABLE sessions ADD COLUMN project_id TEXT")
            model_columns = {
                row["name"] for row in self._connection.execute("PRAGMA table_info(model_configs)")
            }
            if "is_active" not in model_columns:
                self._connection.execute(
                    "ALTER TABLE model_configs ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
                )
            self._normalize_active_model_config()
            self._connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS model_configs_one_active "
                "ON model_configs(is_active) WHERE is_active = 1"
            )
        self._migrate_document_owners_if_needed()

    def _normalize_active_model_config(self) -> None:
        """Make legacy saved configurations conform to the one-active-profile invariant."""
        rows = self._connection.execute(
            "SELECT model_config_id FROM model_configs WHERE is_active = 1 "
            "ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
        if len(rows) == 1:
            return
        candidate = (
            rows[0]
            if rows
            else self._connection.execute(
                "SELECT model_config_id FROM model_configs "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        )
        if candidate is None:
            return
        self._connection.execute("UPDATE model_configs SET is_active = 0")
        self._connection.execute(
            "UPDATE model_configs SET is_active = 1 WHERE model_config_id = ?",
            (candidate["model_config_id"],),
        )

    def _migrate_document_owners_if_needed(self) -> None:
        """Allow the existing document pipeline to persist either session or project owners."""
        with self._lock:
            columns = {
                str(row["name"]): int(row["notnull"])
                for row in self._connection.execute("PRAGMA table_info(documents)")
            }
            if "project_id" in columns and columns.get("session_id") == 0:
                return
            self._connection.execute("PRAGMA foreign_keys=OFF")
            try:
                with self._connection:
                    self._connection.executescript(
                        """
                        CREATE TABLE documents_new (
                            document_id TEXT PRIMARY KEY,
                            attachment_id TEXT NOT NULL UNIQUE,
                            session_id TEXT REFERENCES sessions(session_id),
                            project_id TEXT REFERENCES projects(project_id),
                            blob_id TEXT NOT NULL,
                            name TEXT NOT NULL,
                            media_type TEXT,
                            status TEXT NOT NULL,
                            normalized_text TEXT,
                            error_message TEXT,
                            deleted_at TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            CHECK ((session_id IS NOT NULL AND project_id IS NULL)
                                OR (session_id IS NULL AND project_id IS NOT NULL))
                        );
                        INSERT INTO documents_new(document_id, attachment_id, session_id, blob_id,
                            name, media_type, status, normalized_text, error_message, deleted_at,
                            created_at, updated_at)
                        SELECT document_id, attachment_id, session_id, blob_id, name, media_type,
                            status, normalized_text, error_message, deleted_at, created_at,
                            updated_at
                        FROM documents;
                        CREATE TABLE document_segments_new (
                            segment_id TEXT PRIMARY KEY,
                            document_id TEXT NOT NULL REFERENCES documents_new(document_id),
                            ordinal INTEGER NOT NULL,
                            text TEXT NOT NULL,
                            page INTEGER,
                            section TEXT,
                            UNIQUE(document_id, ordinal)
                        );
                        INSERT INTO document_segments_new
                        SELECT segment_id, document_id, ordinal, text, page, section
                        FROM document_segments;
                        CREATE TABLE document_ingestion_events_new (
                            event_id TEXT PRIMARY KEY,
                            document_id TEXT NOT NULL REFERENCES documents_new(document_id),
                            state TEXT NOT NULL,
                            error_message TEXT,
                            created_at TEXT NOT NULL
                        );
                        INSERT INTO document_ingestion_events_new
                        SELECT event_id, document_id, state, error_message, created_at
                        FROM document_ingestion_events;
                        DROP TABLE document_ingestion_events;
                        DROP TABLE document_segments;
                        DROP TABLE documents;
                        ALTER TABLE documents_new RENAME TO documents;
                        ALTER TABLE document_segments_new RENAME TO document_segments;
                        ALTER TABLE document_ingestion_events_new
                            RENAME TO document_ingestion_events;
                        CREATE INDEX documents_session_visibility
                            ON documents(session_id, status, deleted_at);
                        CREATE INDEX document_segments_document
                            ON document_segments(document_id, ordinal);
                        """
                    )
            finally:
                self._connection.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self._connection.close()

    def create_session(
        self,
        principal_id: str = "local",
        workspace_id: str = "local",
        project_id: str | None = None,
    ) -> str:
        if project_id is not None and self.project(project_id) is None:
            raise KeyError(project_id)
        session_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO sessions(session_id, principal_id, workspace_id, project_id, "
                "created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, principal_id, workspace_id, project_id, _utc_now()),
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

    def session_identity(self, session_id: str) -> dict[str, str | None] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT principal_id, workspace_id, project_id FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def session_summaries(
        self, principal_id: str, workspace_id: str, limit: int = MAX_SESSION_SUMMARIES
    ) -> list[dict[str, str | None]]:
        """Return bounded, scope-owned sidebar data without loading timelines."""
        limit = max(1, min(limit, MAX_SESSION_SUMMARIES))
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT sessions.session_id, sessions.project_id, sessions.created_at,
                       COALESCE(MAX(timeline.created_at), sessions.created_at) AS last_activity_at
                FROM sessions
                LEFT JOIN timeline ON timeline.session_id = sessions.session_id
                WHERE sessions.principal_id = ? AND sessions.workspace_id = ?
                GROUP BY sessions.session_id
                ORDER BY last_activity_at DESC, sessions.session_id DESC
                LIMIT ?
                """,
                (principal_id, workspace_id, limit),
            ).fetchall()
            summaries: list[dict[str, str | None]] = []
            for row in rows:
                title_row = self._connection.execute(
                    """
                    SELECT payload_json FROM timeline
                    WHERE session_id = ? AND kind = 'user_message'
                    ORDER BY created_at, rowid
                    """,
                    (row["session_id"],),
                ).fetchall()
                title = "New chat"
                for title_candidate in title_row:
                    content = json.loads(title_candidate["payload_json"]).get("content")
                    if isinstance(content, str) and (normalized := " ".join(content.split())):
                        title = normalized[:120]
                        break
                summaries.append(
                    {
                        "session_id": str(row["session_id"]),
                        "project_id": row["project_id"],
                        "title": title,
                        "created_at": str(row["created_at"]),
                        "last_activity_at": str(row["last_activity_at"]),
                    }
                )
        return summaries

    def create_project(
        self,
        name: str,
        description: str | None = None,
        instructions: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project_id, now = str(uuid.uuid4()), _utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO projects(project_id, name, description, instructions, metadata_json,
                   created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (project_id, name, description, instructions, json.dumps(metadata or {}), now, now),
            )
        project = self.project(project_id)
        if project is None:
            raise RuntimeError("Project was not persisted")
        return project

    def project(self, project_id: str, include_deleted: bool = False) -> dict[str, Any] | None:
        query = "SELECT * FROM projects WHERE project_id = ?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        with self._lock:
            row = self._connection.execute(query, (project_id,)).fetchone()
        return self._project_row(row) if row else None

    def projects(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY created_at, project_id"
            ).fetchall()
        return [self._project_row(row) for row in rows]

    def update_project(
        self,
        project_id: str,
        name: str,
        description: str | None,
        instructions: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE projects SET name = ?, description = ?, instructions = ?,
                   metadata_json = ?,
                   updated_at = ? WHERE project_id = ? AND deleted_at IS NULL""",
                (name, description, instructions, json.dumps(metadata), _utc_now(), project_id),
            )
        return self.project(project_id) if cursor.rowcount else None

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
        request_id: str | None,
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

    def create_model_config(
        self, provider_type: str, base_url: str, model_id: str, api_key: str | None
    ) -> str:
        model_config_id = str(uuid.uuid4())
        with self._lock, self._connection:
            active_exists = self._connection.execute(
                "SELECT 1 FROM model_configs WHERE is_active = 1 LIMIT 1"
            ).fetchone()
            self._connection.execute(
                """INSERT INTO model_configs(model_config_id, provider_type, base_url, model_id,
                   api_key, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    model_config_id,
                    provider_type,
                    base_url.rstrip("/"),
                    model_id,
                    api_key,
                    0 if active_exists else 1,
                    _utc_now(),
                ),
            )
        return model_config_id

    def upsert_model_config(
        self, provider_type: str, base_url: str, model_id: str, api_key: str | None
    ) -> str:
        """Compatibility name for callers that previously created the one active configuration."""
        return self.create_model_config(provider_type, base_url, model_id, api_key)

    def model_configs(self) -> list[dict[str, str | int | None]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT model_config_id, provider_type, base_url, model_id, api_key, is_active "
                "FROM model_configs ORDER BY is_active DESC, created_at DESC, rowid DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def model_config(self, model_config_id: str) -> dict[str, str | int | None] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT model_config_id, provider_type, base_url, model_id, api_key, is_active "
                "FROM model_configs WHERE model_config_id = ?",
                (model_config_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_model_config(
        self,
        model_config_id: str,
        provider_type: str,
        base_url: str,
        model_id: str,
        api_key: str | None,
    ) -> bool:
        with self._lock, self._connection:
            updated = self._connection.execute(
                "UPDATE model_configs SET provider_type = ?, base_url = ?, model_id = ?, "
                "api_key = COALESCE(?, api_key) WHERE model_config_id = ?",
                (provider_type, base_url.rstrip("/"), model_id, api_key, model_config_id),
            )
        return updated.rowcount == 1

    def activate_model_config(self, model_config_id: str) -> bool:
        with self._lock, self._connection:
            exists = self._connection.execute(
                "SELECT 1 FROM model_configs WHERE model_config_id = ?", (model_config_id,)
            ).fetchone()
            if exists is None:
                return False
            self._connection.execute("UPDATE model_configs SET is_active = 0 WHERE is_active = 1")
            self._connection.execute(
                "UPDATE model_configs SET is_active = 1 WHERE model_config_id = ?",
                (model_config_id,),
            )
        return True

    def delete_model_config(self, model_config_id: str) -> str:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT is_active FROM model_configs WHERE model_config_id = ?", (model_config_id,)
            ).fetchone()
            if row is None:
                return "missing"
            if row["is_active"]:
                return "active"
            self._connection.execute(
                "DELETE FROM model_configs WHERE model_config_id = ?", (model_config_id,)
            )
        return "deleted"

    def active_model_config(self) -> dict[str, str | int | None] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT model_config_id, provider_type, base_url, model_id, api_key, is_active "
                "FROM model_configs "
                "WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # Document metadata and normalized segments deliberately live at this persistence
    # boundary. Blob bytes remain in the opaque local blob store.
    def create_document(
        self,
        document_id: str,
        attachment_id: str,
        session_id: str | None,
        project_id: str | None,
        blob_id: str,
        name: str,
        media_type: str | None,
    ) -> None:
        now = _utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO documents(document_id, attachment_id, session_id, project_id,
                   blob_id,
                   name, media_type, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'uploaded', ?, ?)""",
                (
                    document_id,
                    attachment_id,
                    session_id,
                    project_id,
                    blob_id,
                    name,
                    media_type,
                    now,
                    now,
                ),
            )
            self._record_ingestion_event(document_id, "uploaded", None)

    def set_document_state(
        self, document_id: str, state: str, error_message: str | None = None
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE documents SET status = ?, error_message = ?, updated_at = ? "
                "WHERE document_id = ?",
                (state, error_message, _utc_now(), document_id),
            )
            self._record_ingestion_event(document_id, state, error_message)

    def store_parsed_document(
        self, document_id: str, normalized_text: str, segments: list[dict[str, Any]]
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE documents SET normalized_text = ?, updated_at = ? WHERE document_id = ?",
                (normalized_text, _utc_now(), document_id),
            )
            self._connection.execute(
                "DELETE FROM document_segments WHERE document_id = ?", (document_id,)
            )
            self._connection.executemany(
                """INSERT INTO document_segments(segment_id, document_id, ordinal, text,
                   page, section)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        segment["segment_id"],
                        document_id,
                        segment["ordinal"],
                        segment["text"],
                        segment.get("page"),
                        segment.get("section"),
                    )
                    for segment in segments
                ],
            )

    def document(self, document_id: str, include_deleted: bool = False) -> dict[str, Any] | None:
        query = "SELECT * FROM documents WHERE document_id = ?"
        if not include_deleted:
            query += " AND deleted_at IS NULL"
        with self._lock:
            row = self._connection.execute(query, (document_id,)).fetchone()
        return dict(row) if row else None

    def visible_documents(
        self, session_id: str, attachment_ids: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        if not attachment_ids:
            return []
        placeholders = ", ".join("?" for _ in attachment_ids)
        with self._lock:
            rows = self._connection.execute(
                f"""SELECT * FROM documents WHERE session_id = ?
                AND attachment_id IN ({placeholders})
                AND status = 'ready' AND deleted_at IS NULL ORDER BY created_at, document_id""",
                (session_id, *attachment_ids),
            ).fetchall()
        return [dict(row) for row in rows]

    def visible_project_documents(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT documents.* FROM documents JOIN projects
                   ON projects.project_id = documents.project_id
                   WHERE documents.project_id = ? AND documents.status = 'ready'
                   AND documents.deleted_at IS NULL AND projects.deleted_at IS NULL
                   ORDER BY documents.created_at, documents.document_id""",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def project_documents(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT documents.* FROM documents JOIN projects
                   ON projects.project_id = documents.project_id
                   WHERE documents.project_id = ? AND documents.deleted_at IS NULL
                   AND projects.deleted_at IS NULL
                   ORDER BY documents.created_at, documents.document_id""",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def session_attachment_ids(self, session_id: str) -> tuple[str, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT attachment_id FROM documents WHERE session_id = ? AND deleted_at IS NULL "
                "ORDER BY created_at, document_id",
                (session_id,),
            ).fetchall()
        return tuple(str(row["attachment_id"]) for row in rows)

    def document_segments(
        self, document_id: str, section: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM document_segments WHERE document_id = ?"
        values: tuple[object, ...] = (document_id,)
        if section is not None:
            query += " AND section = ?"
            values = (document_id, section)
        query += " ORDER BY ordinal"
        with self._lock:
            rows = self._connection.execute(query, values).fetchall()
        return [dict(row) for row in rows]

    def delete_document(self, document_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE documents SET deleted_at = ?, updated_at = ? WHERE document_id = ? "
                "AND deleted_at IS NULL",
                (_utc_now(), _utc_now(), document_id),
            )
            if cursor.rowcount:
                self._record_ingestion_event(document_id, "deleted", None)
            return cursor.rowcount == 1

    def document_ingestion_events(self, document_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT state, error_message, created_at FROM document_ingestion_events "
                "WHERE document_id = ? ORDER BY created_at, rowid",
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def incomplete_documents(self) -> list[dict[str, Any]]:
        """Non-tombstoned ingestion work that a normal restart may reconcile."""
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM documents WHERE status IN ('uploaded', 'parsing', 'indexing')
                   AND deleted_at IS NULL ORDER BY created_at, document_id"""
            ).fetchall()
        return [dict(row) for row in rows]

    def _record_ingestion_event(
        self, document_id: str, state: str, error_message: str | None
    ) -> None:
        self._connection.execute(
            """INSERT INTO document_ingestion_events(event_id, document_id, state, error_message,
               created_at) VALUES (?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), document_id, state, error_message, _utc_now()),
        )

    @staticmethod
    def _project_row(row: sqlite3.Row) -> dict[str, Any]:
        project = dict(row)
        project["metadata"] = json.loads(project.pop("metadata_json"))
        project.pop("deleted_at")
        return project
