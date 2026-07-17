from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

_SESSIONS_TABLE = "sessions"


def _get_dsn() -> str | None:
    dsn = os.environ.get("ORION_DATABASE_URL")
    if dsn:
        return dsn
    pg_user = os.environ.get("POSTGRES_USER", "orion")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "orion_dev")
    pg_host = os.environ.get("POSTGRES_HOST", "postgres")
    pg_db = os.environ.get("POSTGRES_DB", "orion")
    if pg_host:
        return f"postgresql://{pg_user}:{pg_pass}@{pg_host}:5432/{pg_db}"
    return None


def _import_driver() -> tuple:
    try:
        import psycopg2

        return psycopg2, None
    except ImportError:
        return None, "psycopg2 not installed"


def init_db(dsn: str | None = None) -> None:
    dsn = dsn or _get_dsn()
    if not dsn:
        return
    driver, err = _import_driver()
    if err:
        return
    conn = driver.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {_SESSIONS_TABLE} (
                    session_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'api',
                    title TEXT DEFAULT '',
                    summary TEXT,
                    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
    finally:
        conn.close()


def load_session(dsn: str, session_id: str) -> dict[str, Any] | None:
    driver, _ = _import_driver()
    if driver is None:
        return None
    conn = driver.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT session_id, source, title, summary, messages FROM {_SESSIONS_TABLE} WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "session_id": row[0],
                "source": row[1],
                "title": row[2] or "",
                "summary": row[3],
                "messages": row[4] if isinstance(row[4], list) else json.loads(row[4]),
            }
    finally:
        conn.close()


def save_session(dsn: str, session_id: str, data: dict[str, Any]) -> None:
    driver, _ = _import_driver()
    if driver is None:
        return
    conn = driver.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_SESSIONS_TABLE} (session_id, source, title, summary, messages, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (session_id)
                DO UPDATE SET
                    source = EXCLUDED.source,
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    messages = EXCLUDED.messages,
                    updated_at = NOW()
                """,
                (
                    session_id,
                    data.get("source", "api"),
                    data.get("title", ""),
                    data.get("summary"),
                    json.dumps(data.get("messages", [])),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def delete_session(dsn: str, session_id: str) -> bool:
    driver, _ = _import_driver()
    if driver is None:
        return False
    conn = driver.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {_SESSIONS_TABLE} WHERE session_id = %s",
                (session_id,),
            )
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


def list_sessions_db(dsn: str) -> list[dict]:
    driver, _ = _import_driver()
    if driver is None:
        return []
    conn = driver.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT session_id, source, title, messages, updated_at FROM {_SESSIONS_TABLE} ORDER BY updated_at DESC LIMIT 50"
            )
            rows = []
            for row in cur.fetchall():
                msgs = row[3] if isinstance(row[3], list) else json.loads(row[3])
                rows.append(
                    {
                        "id": row[0],
                        "source": row[1],
                        "title": row[2] or "",
                        "turns": len([m for m in msgs if m.get("role") == "user"]),
                        "updated": row[4].isoformat() if row[4] else "",
                        "preview": (msgs[:1] or [{}])[0].get("content", "")[:80]
                        if msgs
                        else "",
                    }
                )
            return rows
    finally:
        conn.close()


def rename_session_db(dsn: str, session_id: str, title: str) -> bool:
    driver, _ = _import_driver()
    if driver is None:
        return False
    conn = driver.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {_SESSIONS_TABLE} SET title = %s, updated_at = NOW() WHERE session_id = %s",
                (title, session_id),
            )
            updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


class PostgresConversationStore:
    def __init__(
        self,
        session_id: str,
        dsn: str,
        summarize_fn: Callable[[str], str] | None = None,
        source: str = "api",
    ) -> None:
        self._session_id = session_id
        self._dsn = dsn
        self._source = source
        self._summarize_fn = summarize_fn
        self._mem: list[dict[str, str]] = []
        self._summary: str | None = None
        self._dirty = False
        self._load()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def history(self) -> list[dict[str, str]]:
        if self._summary:
            return [
                {
                    "role": "system",
                    "content": f"Previous conversation summary: {self._summary}",
                }
            ] + self._mem
        return list(self._mem)

    def add_turn(self, user: str, assistant: str) -> None:
        self._mem.append({"role": "user", "content": user})
        self._mem.append({"role": "assistant", "content": assistant})
        self._dirty = True
        self._save()

    def add_classifier_turn(self, user: str, label: str) -> None:
        self._mem.append({"role": "user", "content": user})
        self._mem.append({"role": "assistant", "content": f"[classified as {label}]"})
        self._dirty = True
        self._save()

    def set_summarize_fn(self, fn: Callable[[str], str]) -> None:
        self._summarize_fn = fn

    def set_summary(self, summary: str) -> None:
        self._summary = summary
        self._dirty = True

    @property
    def summary(self) -> str | None:
        return self._summary

    def _load(self) -> None:
        data = load_session(self._dsn, self._session_id)
        if data is None:
            return
        self._mem = data.get("messages", [])
        self._summary = data.get("summary")

    def _save(self) -> None:
        if not self._dirty:
            return
        data = {
            "session_id": self._session_id,
            "source": self._source,
            "messages": self._mem,
        }
        if self._summary:
            data["summary"] = self._summary
        save_session(self._dsn, self._session_id, data)
        self._dirty = False
