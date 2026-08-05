from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from typing import Any

from src.agent.conversation_store import ConversationStore
from src.pipeline.retry import RetryExecutor, RetryPolicy

_SESSIONS_TABLE = "sessions"
_DOCUMENTS_TABLE = "documents"

# ---- Connection pool ----

_pool_dsn: str | None = None
_pool_connections: list = []
_pool_lock = threading.Lock()
_pool_semaphore: threading.Semaphore | None = None

_MAX_POOL_SIZE = int(os.environ.get("ORION_DB_POOL_SIZE", "5"))
_MIN_POOL_SIZE = int(os.environ.get("ORION_DB_MIN_POOL_SIZE", "1"))
_RETRY_MAX_ATTEMPTS = 3

_db_retry = RetryExecutor(
    RetryPolicy(
        max_attempts=_RETRY_MAX_ATTEMPTS,
        backoff_base=0.5,
        retryable_exceptions=(Exception,),  # psycopg2 raises its own types
    ),
)


def _mask_dsn(dsn: str) -> str:
    return re.sub(r"(postgresql://[^:]+:)([^@]+)(@)", r"\1***\3", dsn)


def _build_dsn(
    user: str,
    password: str,
    host: str,
    db: str,
    ssl: bool = False,
) -> str:
    """Build a PostgreSQL connection string from components."""
    dsn = f"postgresql://{user}:{password}@{host}:5432/{db}"
    if ssl:
        dsn += "?sslmode=require"
    return dsn


def _get_dsn() -> str | None:
    dsn = os.environ.get("ORION_DATABASE_URL")
    if dsn:
        if os.environ.get("ORION_DB_SSL") == "1" and "sslmode" not in dsn:
            dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
        return dsn
    pg_user = os.environ.get("POSTGRES_USER", "orion")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "")
    pg_host = os.environ.get("POSTGRES_HOST", "")
    pg_db = os.environ.get("POSTGRES_DB", "orion")
    if pg_host and pg_pass:
        ssl = os.environ.get("ORION_DB_SSL") == "1"
        return _build_dsn(pg_user, pg_pass, pg_host, pg_db, ssl)
    return None


def _import_driver() -> tuple:
    try:
        import psycopg2

        return psycopg2, None
    except ImportError:
        return None, "psycopg2 not installed"


def _init_pool(dsn: str) -> None:
    """Initialize (or reset) the connection pool for the given DSN."""
    global _pool_dsn, _pool_semaphore, _pool_connections  # noqa: PLW0603

    driver, err = _import_driver()
    if err:
        return

    with _pool_lock:
        # Always reset pool — stale connections from previous runs won't work
        for conn in _pool_connections:
            try:
                conn.close()
            except Exception:
                pass
        _pool_connections.clear()
        _pool_semaphore = threading.Semaphore(_MAX_POOL_SIZE)
        _pool_dsn = dsn


def _get_conn(dsn: str):
    """Get a connection from the pool, or create directly if pool not initialized."""
    driver, err = _import_driver()
    if driver is None:
        msg = err or "psycopg2 not installed"
        raise RuntimeError(msg)

    if _pool_semaphore is None:
        return driver.connect(dsn)

    acquired = _pool_semaphore.acquire(timeout=10)
    if not acquired:
        raise RuntimeError("Timed out waiting for database connection from pool")

    with _pool_lock:
        if _pool_connections:
            return _pool_connections.pop()

    # Pool was empty; create a new connection
    return _connect_with_retry(driver, dsn)


def _put_conn(conn) -> None:
    """Return a connection to the pool, or close it if pool is full."""
    if _pool_semaphore is None:
        try:
            conn.close()
        except Exception:
            pass
        return

    with _pool_lock:
        if len(_pool_connections) < _MAX_POOL_SIZE:
            _pool_connections.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass

    _pool_semaphore.release()


def _connect_with_retry(driver, dsn: str):
    """Connect to PostgreSQL with exponential backoff retry (unified policy)."""
    return _db_retry.execute(
        lambda: driver.connect(dsn),
        context="postgresql_connect",
    )


def _execute_with_pool(dsn: str, fn: Callable[..., Any], *args: Any) -> Any:
    """Execute a function with a pooled connection, returning connection after use."""
    conn = _get_conn(dsn)
    try:
        return fn(conn, *args)
    finally:
        _put_conn(conn)


# ---- Public API ----


def init_db(dsn: str | None = None) -> None:
    dsn = dsn or _get_dsn()
    if not dsn:
        return
    driver, err = _import_driver()
    if err:
        return
    _init_pool(dsn)
    conn = _get_conn(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {_SESSIONS_TABLE} (
                    session_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'api',
                    title TEXT DEFAULT '',
                    summary TEXT,
                    investigation_context JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute(
                f"ALTER TABLE {_SESSIONS_TABLE} ADD COLUMN IF NOT EXISTS "
                "investigation_context JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
        conn.commit()
    finally:
        _put_conn(conn)


def load_session(dsn: str, session_id: str) -> dict[str, Any] | None:
    driver, _ = _import_driver()
    if driver is None:
        return None

    def _do_load(conn, sid: str) -> dict[str, Any] | None:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT session_id, source, title, summary, messages, "
                f"investigation_context FROM {_SESSIONS_TABLE} WHERE session_id = %s",
                (sid,),
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
                "investigation_context": (
                    row[5] if isinstance(row[5], dict) else json.loads(row[5] or "{}")
                ),
            }

    return _execute_with_pool(dsn, _do_load, session_id)


def save_session(dsn: str, session_id: str, data: dict[str, Any]) -> None:
    driver, _ = _import_driver()
    if driver is None:
        return

    def _do_save(conn, sid: str, d: dict[str, Any]) -> None:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_SESSIONS_TABLE} (
                    session_id, source, title, summary, messages,
                    investigation_context, updated_at
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                ON CONFLICT (session_id)
                DO UPDATE SET
                    source = EXCLUDED.source,
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    messages = EXCLUDED.messages,
                    investigation_context = EXCLUDED.investigation_context,
                    updated_at = NOW()
                """,
                (
                    sid,
                    d.get("source", "api"),
                    d.get("title", ""),
                    d.get("summary"),
                    json.dumps(d.get("messages", [])),
                    json.dumps(d.get("investigation_context", {})),
                ),
            )
        conn.commit()

    _execute_with_pool(dsn, _do_save, session_id, data)


def delete_session(dsn: str, session_id: str) -> bool:
    driver, _ = _import_driver()
    if driver is None:
        return False

    def _do_delete(conn, sid: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {_SESSIONS_TABLE} WHERE session_id = %s",
                (sid,),
            )
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted

    return _execute_with_pool(dsn, _do_delete, session_id)


def list_sessions_db(dsn: str) -> list[dict]:
    driver, _ = _import_driver()
    if driver is None:
        return []

    def _do_list(conn) -> list[dict]:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT session_id, source, title, messages, updated_at FROM {_SESSIONS_TABLE} ORDER BY updated_at DESC LIMIT 50"
            )
            rows = []
            for row in cur.fetchall():
                msgs = row[3] if isinstance(row[3], list) else json.loads(row[3])
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
                rows.append(
                    {
                        "id": row[0],
                        "source": row[1],
                        "title": row[2] or "",
                        "turns": len([m for m in real_msgs if m.get("role") == "user"]),
                        "updated": row[4].isoformat() if row[4] else "",
                        "preview": (
                            (real_msgs[:1] or [{}])[0].get("content", "")[:80]
                            if real_msgs
                            else ""
                        ),
                        "messages": real_msgs,
                    }
                )
            return rows

    return _execute_with_pool(dsn, _do_list)


def rename_session_db(dsn: str, session_id: str, title: str) -> bool:
    driver, _ = _import_driver()
    if driver is None:
        return False

    def _do_rename(conn, sid: str, t: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {_SESSIONS_TABLE} SET title = %s, updated_at = NOW() WHERE session_id = %s",
                (t, sid),
            )
            updated = cur.rowcount > 0
        conn.commit()
        return updated

    return _execute_with_pool(dsn, _do_rename, session_id, title)


def init_documents_db(dsn: str | None = None) -> None:
    dsn = dsn or _get_dsn()
    if not dsn:
        return
    driver, err = _import_driver()
    if err:
        return
    _init_pool(dsn)
    conn = _get_conn(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {_DOCUMENTS_TABLE} (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    storage_path TEXT NOT NULL,
                    session_id TEXT,
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
    finally:
        _put_conn(conn)


def insert_document(
    dsn: str,
    doc_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> bool:
    driver, _ = _import_driver()
    if driver is None:
        return False

    def _do_insert(conn, *args) -> bool:
        did, fn, ct, sb, sp, sid, meta = args
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_DOCUMENTS_TABLE}
                    (id, filename, content_type, size_bytes, storage_path, session_id, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO NOTHING
                """,
                (did, fn, ct, sb, sp, sid, json.dumps(meta or {})),
            )
        conn.commit()
        return cur.rowcount > 0

    return _execute_with_pool(
        dsn,
        _do_insert,
        doc_id,
        filename,
        content_type,
        size_bytes,
        storage_path,
        session_id,
        metadata,
    )


def get_document(dsn: str, doc_id: str) -> dict | None:
    driver, _ = _import_driver()
    if driver is None:
        return None

    def _do_get(conn, did: str) -> dict | None:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, filename, content_type, size_bytes, storage_path, session_id, metadata, created_at FROM {_DOCUMENTS_TABLE} WHERE id = %s",
                (did,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            meta = (
                row[6]
                if isinstance(row[6], dict)
                else json.loads(row[6])
                if row[6]
                else {}
            )
            return {
                "id": row[0],
                "filename": row[1],
                "content_type": row[2],
                "size_bytes": row[3],
                "storage_path": row[4],
                "session_id": row[5],
                "metadata": meta,
                "created_at": row[7].isoformat() if row[7] else "",
            }

    return _execute_with_pool(dsn, _do_get, doc_id)


def list_documents(
    dsn: str,
    session_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    driver, _ = _import_driver()
    if driver is None:
        return []

    def _do_list(conn, sid: str | None, lim: int) -> list[dict]:
        with conn.cursor() as cur:
            if sid:
                cur.execute(
                    f"SELECT id, filename, content_type, size_bytes, session_id, created_at FROM {_DOCUMENTS_TABLE} WHERE session_id = %s ORDER BY created_at DESC LIMIT %s",
                    (sid, lim),
                )
            else:
                cur.execute(
                    f"SELECT id, filename, content_type, size_bytes, session_id, created_at FROM {_DOCUMENTS_TABLE} ORDER BY created_at DESC LIMIT %s",
                    (lim,),
                )
            rows = []
            for row in cur.fetchall():
                rows.append(
                    {
                        "id": row[0],
                        "filename": row[1],
                        "content_type": row[2],
                        "size_bytes": row[3],
                        "session_id": row[4],
                        "created_at": row[5].isoformat() if row[5] else "",
                    }
                )
            return rows

    return _execute_with_pool(dsn, _do_list, session_id, limit)


def delete_document(dsn: str, doc_id: str) -> bool:
    driver, _ = _import_driver()
    if driver is None:
        return False

    def _do_delete(conn, did: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {_DOCUMENTS_TABLE} WHERE id = %s",
                (did,),
            )
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted

    return _execute_with_pool(dsn, _do_delete, doc_id)


class PostgresConversationStore(ConversationStore):
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
        self._mem: list[dict[str, Any]] = []
        self._summary: str | None = None
        self._title: str = ""
        from src.agent.session_investigation_context import SessionInvestigationContext

        self._investigation_context = SessionInvestigationContext()
        self._dirty = False
        self._lock = threading.RLock()
        self._load()

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

    def add_turn(self, user: str, assistant: str) -> None:
        with self._lock:
            self._mem.append({"role": "user", "content": user})
            self._mem.append({"role": "assistant", "content": assistant})
            self._dirty = True
            self._save()
            self._check_compress()

    def truncate_for_regeneration(
        self, turn_index: int
    ) -> list[dict[str, Any]] | None:
        from src.agent.conversation_store import regeneration_start_index

        with self._lock:
            start = regeneration_start_index(self._mem, turn_index)
            if start is None:
                return None
            snapshot = list(self._mem)
            self._mem = self._mem[:start]
            self._dirty = True
            self._save()
            return snapshot

    def restore_messages(self, messages: list[dict[str, Any]]) -> None:
        with self._lock:
            self._mem = list(messages)
            self._dirty = True
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
                self._dirty = True
                self._save()

    def add_classifier_turn(self, user: str, label: str) -> None:
        with self._lock:
            self._mem.append({"role": "user", "content": user})
            self._mem.append(
                {"role": "assistant", "content": f"[classified as {label}]"}
            )
            self._dirty = True
            self._save()
            self._check_compress()

    def set_summarize_fn(self, fn: Callable[[str], str]) -> None:
        with self._lock:
            self._summarize_fn = fn

    def set_summary(self, summary: str) -> None:
        with self._lock:
            self._summary = summary
            self._dirty = True

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

    @property
    def investigation_context(self) -> object:
        with self._lock:
            return self._investigation_context

    def set_investigation_context(self, context: object) -> None:
        from src.agent.session_investigation_context import SessionInvestigationContext

        if not isinstance(context, SessionInvestigationContext):
            raise TypeError("context must be a SessionInvestigationContext")
        with self._lock:
            self._investigation_context = context
            self._dirty = True
            self._save()

    def _load(self) -> None:
        data = load_session(self._dsn, self._session_id)
        if data is None:
            return
        self._mem = data.get("messages", [])
        self._summary = data.get("summary")
        from src.agent.session_investigation_context import SessionInvestigationContext

        self._investigation_context = SessionInvestigationContext.from_dict(
            data.get("investigation_context")
        )
        self._title = data.get("title", "")
        loaded_source = data.get("source")
        if loaded_source:
            self._source = loaded_source

    def _save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            data: dict[str, Any] = {
                "session_id": self._session_id,
                "source": self._source,
                "title": self._title,
                "messages": self._mem,
            }
            if self._summary:
                data["summary"] = self._summary
            data["investigation_context"] = self._investigation_context.to_dict()
            save_session(self._dsn, self._session_id, data)
            self._dirty = False
