"""Atomic hash-only native owner sessions; no bearer/enrollment secret bytes in SQL."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from typing import Any


class NativeAuthPersistence:
    _connection: sqlite3.Connection
    _lock: threading.RLock

    def _create_native_auth_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS native_enrollments (
                    digest TEXT PRIMARY KEY, principal_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL, expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS native_sessions (
                    session_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL, name TEXT NOT NULL, platform TEXT NOT NULL,
                    access_digest TEXT NOT NULL UNIQUE, access_expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                    revoked_at INTEGER, rotations INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS native_session_owner
                    ON native_sessions(principal_id, workspace_id);
                CREATE TABLE IF NOT EXISTS native_refresh_tokens (
                    digest TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL
                        REFERENCES native_sessions(session_id) ON DELETE CASCADE,
                    used INTEGER NOT NULL DEFAULT 0 CHECK(used IN (0,1))
                );
                CREATE INDEX IF NOT EXISTS native_refresh_session
                    ON native_refresh_tokens(session_id);
            """)

    def _prune_native_auth(self, now: int) -> None:
        # First write acquires SQLite's writer transaction before subsequent
        # capacity/consume/rotation reads, including across separate connections.
        self._connection.execute("DELETE FROM native_enrollments WHERE expires_at<=?", (now,))
        self._connection.execute("DELETE FROM native_sessions WHERE expires_at<=?", (now,))

    def create_native_enrollment(
        self, digest: str, principal: str, workspace: str, expires: int, now: int
    ) -> bool:
        with self._lock, self._connection:
            self._prune_native_auth(now)
            if (
                self._connection.execute("SELECT count(*) FROM native_enrollments").fetchone()[0]
                >= 8
            ):
                return False
            self._connection.execute(
                "INSERT INTO native_enrollments VALUES (?,?,?,?)",
                (digest, principal, workspace, expires),
            )
        return True

    def consume_native_enrollment(
        self,
        digest: str,
        name: str,
        platform: str,
        access: str,
        refresh: str,
        now: int,
        access_expires: int,
        expires: int,
    ) -> dict[str, Any] | None:
        with self._lock, self._connection:
            self._prune_native_auth(now)
            code = self._connection.execute(
                "SELECT principal_id,workspace_id FROM native_enrollments WHERE digest=?", (digest,)
            ).fetchone()
            if code is None:
                return None
            if self._connection.execute("SELECT count(*) FROM native_sessions").fetchone()[0] >= 64:
                return None
            if (
                self._connection.execute(
                    "DELETE FROM native_enrollments WHERE digest=?", (digest,)
                ).rowcount
                != 1
            ):
                return None
            session = uuid.uuid4().hex
            self._connection.execute(
                "INSERT INTO native_sessions VALUES (?,?,?,?,?,?,?,?,?,NULL,0)",
                (
                    session,
                    code["principal_id"],
                    code["workspace_id"],
                    name,
                    platform,
                    access,
                    access_expires,
                    now,
                    expires,
                ),
            )
            self._connection.execute(
                "INSERT INTO native_refresh_tokens(digest,session_id) VALUES (?,?)",
                (refresh, session),
            )
        return {"session_id": session, "access_expires_at": access_expires, "expires_at": expires}

    def rotate_native_refresh(
        self,
        digest: str,
        access: str,
        refresh: str,
        now: int,
        access_expires: int,
    ) -> tuple[str, dict[str, Any] | None]:
        with self._lock, self._connection:
            self._prune_native_auth(now)
            row = self._connection.execute(
                "SELECT s.session_id,s.expires_at,s.revoked_at,s.rotations,t.used "
                "FROM native_refresh_tokens t JOIN native_sessions s ON s.session_id=t.session_id "
                "WHERE t.digest=?",
                (digest,),
            ).fetchone()
            if row is None or row["revoked_at"] is not None:
                return "invalid_refresh", None
            if row["used"] or row["rotations"] >= 4096:
                self._connection.execute(
                    "UPDATE native_sessions SET revoked_at=? WHERE session_id=?",
                    (now, row["session_id"]),
                )
                # Return after the transaction commits; raising here would roll
                # back replay revocation and accidentally leave access usable.
                return "refresh_replayed" if row["used"] else "rotation_limit", None
            expiry = min(access_expires, row["expires_at"])
            self._connection.execute(
                "UPDATE native_refresh_tokens SET used=1 WHERE digest=?", (digest,)
            )
            self._connection.execute(
                "INSERT INTO native_refresh_tokens(digest,session_id) VALUES (?,?)",
                (refresh, row["session_id"]),
            )
            self._connection.execute(
                "UPDATE native_sessions SET access_digest=?,access_expires_at=?,"
                "rotations=rotations+1 "
                "WHERE session_id=?",
                (access, expiry, row["session_id"]),
            )
        return "rotated", {
            "session_id": row["session_id"],
            "access_expires_at": expiry,
            "expires_at": row["expires_at"],
        }

    def native_access_identity(self, digest: str, now: int) -> dict[str, str] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT session_id,principal_id,workspace_id FROM native_sessions "
                "WHERE access_digest=? AND access_expires_at>? AND expires_at>? "
                "AND revoked_at IS NULL",
                (digest, now, now),
            ).fetchone()
        return dict(row) if row else None

    def native_owner_sessions(self, principal: str, workspace: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT session_id,name,platform,created_at,expires_at,revoked_at "
                "FROM native_sessions WHERE principal_id=? AND workspace_id=? "
                "ORDER BY created_at,session_id LIMIT 64",
                (principal, workspace),
            ).fetchall()
        return [dict(row) for row in rows]

    def native_session_active(self, session: str, principal: str, workspace: str, now: int) -> bool:
        with self._lock:
            return (
                self._connection.execute(
                    "SELECT 1 FROM native_sessions WHERE session_id=? AND principal_id=? "
                    "AND workspace_id=? AND expires_at>? AND revoked_at IS NULL",
                    (session, principal, workspace, now),
                ).fetchone()
                is not None
            )

    def revoke_native_session(self, session: str, principal: str, workspace: str, now: int) -> bool:
        with self._lock, self._connection:
            return (
                self._connection.execute(
                    "UPDATE native_sessions SET revoked_at=COALESCE(revoked_at,?) "
                    "WHERE session_id=? AND principal_id=? AND workspace_id=?",
                    (now, session, principal, workspace),
                ).rowcount
                == 1
            )
