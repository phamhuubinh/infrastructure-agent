"""SQLite-backed conversation store replacing JSON files as default persistence.

Features:
- WAL mode for concurrent read/write
- FTS5 full-text search across sessions (manually synced)
- Thread-safe (connection per thread with check_same_thread=False)
- Zero-config (no external daemon)
- Same interface as PostgresConversationStore for drop-in compatibility
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.conversation_store import regeneration_start_index
from src.shared.logger import info


def _get_default_db_path() -> Path:
    """Return the default SQLite database path."""
    return Path.home() / ".orion" / "sessions.db"


class SQLiteConversationStore:
    """SQLite-backed conversation store.

    Drop-in replacement for both ConversationStore (JSON files) and
    PostgresConversationStore.  Used as the default persistence backend.

    Attributes:
        session_id: Unique session identifier.
        history: List of {"role": ..., "content": ...} dicts.
        summary: Optional LLM-generated conversation summary.
        title: Optional session title.
    """

    def __init__(
        self,
        session_id: str,
        db_path: Path | str | None = None,
        summarize_fn: Callable[[str], str] | None = None,
        source: str = "terminal",
    ) -> None:
        self._session_id = session_id
        self._source = source
        self._db_path = Path(db_path) if db_path else _get_default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._summarize_fn = summarize_fn
        self._mem: list[dict[str, Any]] = []
        self._summary: str | None = None
        self._title: str = ""
        self._lock = threading.RLock()

        # Thread-local connections for WAL mode safety
        self._local = threading.local()

        # Ensure schema exists
        conn = self._get_conn()
        self._ensure_schema(conn)

        # Load any existing session data
        self._load()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                isolation_level=None,  # autocommit mode
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return self._local.conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create tables and FTS5 index if they don't exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'terminal',
                title TEXT DEFAULT '',
                summary TEXT,
                messages TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # FTS5 full-text search — manually synced in _save().
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                session_id UNINDEXED,
                title,
                content,
                tokenize='unicode61'
            )
        """)

    # ------------------------------------------------------------------
    # Properties (matching ConversationStore / PostgresConversationStore)
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._summary:
                return [
                    {
                        "role": "system",
                        "content": f"Previous conversation summary: {self._summary}",
                    }
                ] + list(self._mem)
            return list(self._mem)

    @property
    def title(self) -> str:
        with self._lock:
            return self._title

    def set_title(self, value: str) -> None:
        with self._lock:
            self._title = value

    @property
    def summary(self) -> str | None:
        with self._lock:
            return self._summary

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------

    def add_turn(self, user: str, assistant: str) -> None:
        with self._lock:
            self._mem.append({"role": "user", "content": user})
            self._mem.append({"role": "assistant", "content": assistant})
            self._save()
            self._check_compress()

    def truncate_for_regeneration(
        self, turn_index: int
    ) -> list[dict[str, Any]] | None:
        with self._lock:
            start = regeneration_start_index(self._mem, turn_index)
            if start is None:
                return None
            snapshot = list(self._mem)
            self._mem = self._mem[:start]
            self._save()
            return snapshot

    def restore_messages(self, messages: list[dict[str, Any]]) -> None:
        with self._lock:
            self._mem = list(messages)
            self._save()

    def set_last_response_time(
        self, response_time_ms: int, asked_at: str | None = None
    ) -> None:
        with self._lock:
            assistant_updated = False
            for message in reversed(self._mem):
                role = message.get("role")
                if not assistant_updated and role == "assistant":
                    message["response_time_ms"] = max(0, int(response_time_ms))
                    assistant_updated = True
                elif assistant_updated and asked_at is not None and role == "user":
                    message["asked_at"] = asked_at
                    break
            if assistant_updated:
                self._save()

    def add_classifier_turn(self, user: str, label: str) -> None:
        with self._lock:
            self._mem.append({"role": "user", "content": user})
            self._mem.append(
                {"role": "assistant", "content": f"[classified as {label}]"}
            )
            self._save()
            self._check_compress()

    # ------------------------------------------------------------------
    # Summary management
    # ------------------------------------------------------------------

    def set_summarize_fn(self, fn: Callable[[str], str]) -> None:
        with self._lock:
            self._summarize_fn = fn

    def set_summary(self, summary: str) -> None:
        with self._lock:
            self._summary = summary

    def summarize(self) -> None:
        """Summarize current conversation using the configured summarize_fn."""
        with self._lock:
            all_turns = list(self._mem)
            previous_summary = self._summary
            summarize_fn = self._summarize_fn

        if not all_turns:
            return

        # Build the summarization prompt
        from src.agent.conversation_store import _SUMMARIZE_SYSTEM_PROMPT

        new_turns_text = "\n".join(
            f"{m['role']}: {m['content'][:500]}" for m in all_turns
        )
        prompt = _SUMMARIZE_SYSTEM_PROMPT.format(
            previous_summary=previous_summary or "None",
            new_turns=new_turns_text,
        )

        try:
            if summarize_fn:
                new_summary = summarize_fn(prompt).strip()
            else:
                new_summary = ""
        except Exception as exc:
            info(
                "session",
                session=self._session_id,
                error=str(exc)[:80],
                message="Summarization failed, keeping full history",
            )
            return

        if not new_summary:
            return

        # Keep only turns that arrived after the snapshot was taken
        with self._lock:
            len_before = len(all_turns)
            if self._mem[:len_before] == all_turns:
                self._mem = self._mem[len_before:]
            self._summary = new_summary
            self._save()
        info(
            "session",
            session=self._session_id,
            summary_length=len(self._summary),
            message="Conversation summarized via LLM",
        )

    # ------------------------------------------------------------------
    # Compression trigger
    # ------------------------------------------------------------------

    def _check_compress(self) -> None:
        turn_count = 0
        for i, m in enumerate(self._mem):
            if m["role"] == "user":
                next_msg = self._mem[i + 1] if i + 1 < len(self._mem) else None
                if next_msg is None or not next_msg.get("content", "").startswith(
                    "[classified as"
                ):
                    turn_count += 1

        from src.shared.config import get_config

        threshold = int(get_config().env("ORION_CONVERSATION_THRESHOLD", "50"))
        if turn_count >= threshold:
            self.summarize()

    # ------------------------------------------------------------------
    # Persistence (load / save)
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT source, title, summary, messages FROM sessions WHERE session_id = ?",
                (self._session_id,),
            ).fetchone()

        if row is None:
            return

        self._source = row["source"] or "terminal"
        self._title = row["title"] or ""
        self._summary = row["summary"] or None

        try:
            messages = json.loads(row["messages"])
            if isinstance(messages, list):
                self._mem = messages
        except (json.JSONDecodeError, TypeError):
            self._mem = []

        info(
            "session",
            session=self._session_id,
            messages=len(self._mem),
            has_summary=self._summary is not None,
            title=self._title,
            message="Session loaded from SQLite",
        )

    def _save(self) -> None:
        with self._lock:
            self._save_locked()

    def persist(self) -> None:
        """Ensure an empty session is visible to list/delete APIs."""
        self._save()

    def _save_locked(self) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()

        # 1. Upsert the session row.
        conn.execute(
            """
            INSERT INTO sessions (session_id, source, title, summary, messages, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                source = excluded.source,
                title = excluded.title,
                summary = excluded.summary,
                messages = excluded.messages,
                updated_at = excluded.updated_at
            """,
            (
                self._session_id,
                self._source,
                self._title,
                self._summary,
                json.dumps(self._mem, ensure_ascii=False),
                now,
            ),
        )

        # 2. Update FTS5 index: delete old entry + insert new.
        conn.execute(
            "DELETE FROM sessions_fts WHERE session_id = ?",
            (self._session_id,),
        )
        # Build content string for FTS: title + all message contents.
        content_parts = [self._title]
        for m in self._mem:
            content_parts.append(m.get("content", ""))
        fts_content = " ".join(content_parts)

        conn.execute(
            "INSERT INTO sessions_fts (session_id, title, content) VALUES (?, ?, ?)",
            (self._session_id, self._title, fts_content),
        )

    # ------------------------------------------------------------------
    # Static helpers — list, delete, search, rename
    # ------------------------------------------------------------------

    @staticmethod
    def list_sessions(db_path: Path | str | None = None) -> list[dict[str, Any]]:
        """List all sessions from the SQLite database.

        Returns a list of session summary dicts, same format as
        ``conversation_store.list_sessions()``.
        """
        path = Path(db_path) if db_path else _get_default_db_path()
        if not path.exists():
            return []

        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT session_id, source, title, messages, updated_at "
                "FROM sessions ORDER BY updated_at DESC LIMIT 50"
            ).fetchall()

            sessions = []
            for row in rows:
                try:
                    msgs = json.loads(row["messages"])
                except (json.JSONDecodeError, TypeError):
                    msgs = []

                # Filter out classifier pairs
                real_msgs = []
                skip_next = False
                for i, m in enumerate(msgs):
                    if skip_next:
                        skip_next = False
                        continue
                    if (
                        isinstance(m, dict)
                        and m.get("role") == "user"
                        and i + 1 < len(msgs)
                        and isinstance(msgs[i + 1], dict)
                        and msgs[i + 1].get("role") == "assistant"
                        and msgs[i + 1].get("content", "").startswith("[classified as")
                    ):
                        skip_next = True
                        continue
                    real_msgs.append(m)

                sessions.append(
                    {
                        "id": row["session_id"],
                        "title": row["title"] or "",
                        "source": row["source"] or "terminal",
                        "updated": row["updated_at"] or "",
                        "turns": len([m for m in real_msgs if m.get("role") == "user"]),
                        "preview": (
                            (real_msgs[:1] or [{}])[0].get("content", "")[:80]
                            if real_msgs
                            else ""
                        ),
                        "has_summary": False,
                        "messages": real_msgs,
                    }
                )
            return sessions
        finally:
            conn.close()

    @staticmethod
    def delete_session(session_id: str, db_path: Path | str | None = None) -> bool:
        """Delete a session from the SQLite database. Returns True if deleted."""
        path = Path(db_path) if db_path else _get_default_db_path()
        if not path.exists():
            return False

        conn = sqlite3.connect(str(path))
        try:
            # Delete from FTS5 first, then the main table.
            conn.execute(
                "DELETE FROM sessions_fts WHERE session_id = ?",
                (session_id,),
            )
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    @staticmethod
    def rename_session(
        session_id: str, title: str, db_path: Path | str | None = None
    ) -> bool:
        """Rename a session. Returns True if the session existed and was updated."""
        path = Path(db_path) if db_path else _get_default_db_path()
        if not path.exists():
            return False

        conn = sqlite3.connect(str(path))
        try:
            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (title, now, session_id),
            )
            updated = cursor.rowcount > 0
            if updated:
                # Sync FTS5 title
                conn.execute(
                    "UPDATE sessions_fts SET title = ? WHERE session_id = ?",
                    (title, session_id),
                )
            conn.commit()
            return updated
        finally:
            conn.close()

    @staticmethod
    def search_sessions(
        query: str, db_path: Path | str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Full-text search across sessions using FTS5.

        Returns matching sessions ordered by relevance.
        """
        path = Path(db_path) if db_path else _get_default_db_path()
        if not path.exists():
            return []

        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT s.session_id, s.source, s.title, s.messages, s.updated_at,
                       rank
                FROM sessions_fts f
                JOIN sessions s ON s.session_id = f.session_id
                WHERE sessions_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()

            sessions = []
            for row in rows:
                try:
                    msgs = json.loads(row["messages"])
                except (json.JSONDecodeError, TypeError):
                    msgs = []

                real_msgs = []
                skip_next = False
                for i, m in enumerate(msgs):
                    if skip_next:
                        skip_next = False
                        continue
                    if (
                        isinstance(m, dict)
                        and m.get("role") == "user"
                        and i + 1 < len(msgs)
                        and isinstance(msgs[i + 1], dict)
                        and msgs[i + 1].get("role") == "assistant"
                        and msgs[i + 1].get("content", "").startswith("[classified as")
                    ):
                        skip_next = True
                        continue
                    real_msgs.append(m)

                sessions.append(
                    {
                        "id": row["session_id"],
                        "title": row["title"] or "",
                        "source": row["source"] or "terminal",
                        "updated": row["updated_at"] or "",
                        "turns": len([m for m in real_msgs if m.get("role") == "user"]),
                        "preview": (
                            (real_msgs[:1] or [{}])[0].get("content", "")[:80]
                            if real_msgs
                            else ""
                        ),
                        "messages": real_msgs,
                    }
                )
            return sessions
        finally:
            conn.close()


# ------------------------------------------------------------------
# JSON → SQLite migration
# ------------------------------------------------------------------


def migrate_json_to_sqlite(
    json_dir: Path | str | None = None,
    sqlite_path: Path | str | None = None,
) -> int:
    """One-time import of existing JSON sessions into SQLite.

    Args:
        json_dir: Directory containing JSON session files.
                  Defaults to ~/.orion/sessions/.
        sqlite_path: Path to the SQLite database.
                     Defaults to ~/.orion/sessions.db.

    Returns:
        Number of sessions migrated.
    """
    json_path = Path(json_dir) if json_dir else Path.home() / ".orion" / "sessions"
    db_path = Path(sqlite_path) if sqlite_path else _get_default_db_path()

    if not json_path.exists():
        info(
            "migration", message="No JSON sessions directory found, skipping migration"
        )
        return 0

    json_files = sorted(json_path.glob("*.json"))
    if not json_files:
        return 0

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        # Ensure schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'terminal',
                title TEXT DEFAULT '',
                summary TEXT,
                messages TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                session_id UNINDEXED,
                title,
                content,
                tokenize='unicode61'
            )
        """)

        migrated = 0
        for json_file in json_files:
            try:
                data = json.loads(json_file.read_text())
                sid = data.get("session_id", json_file.stem)
                source = data.get("source", "terminal")
                title = data.get("title", "")
                summary = data.get("summary")
                messages = json.dumps(data.get("messages", []), ensure_ascii=False)
                updated_at = data.get(
                    "updated_at", datetime.now(timezone.utc).isoformat()
                )

                conn.execute(
                    """
                    INSERT OR REPLACE INTO sessions
                        (session_id, source, title, summary, messages, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (sid, source, title, summary, messages, updated_at),
                )

                # Build FTS5 content
                fts_content = title + " " + messages

                conn.execute(
                    "DELETE FROM sessions_fts WHERE session_id = ?",
                    (sid,),
                )
                conn.execute(
                    "INSERT INTO sessions_fts (session_id, title, content) VALUES (?, ?, ?)",
                    (sid, title, fts_content),
                )

                migrated += 1
            except Exception as exc:
                info(
                    "migration",
                    message=f"Failed to migrate {json_file.name}: {exc}",
                )

        conn.commit()
        info("migration", message=f"Migrated {migrated} sessions from JSON to SQLite")
        return migrated
    finally:
        conn.close()
