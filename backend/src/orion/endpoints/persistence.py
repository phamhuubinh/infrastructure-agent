"""Additive SQLite endpoint identities and bounded payload-free administration audit."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections.abc import Callable
from typing import Any

from orion.persistence.sqlite import SQLiteStore
from orion_endpoint.protocol import Hello


class EndpointStore:
    def __init__(self, store: SQLiteStore, clock: Callable[[], float] = time.time) -> None:
        self.store = store
        self.clock = clock
        self.failures: list[float] = []
        with store._lock, store._connection:
            store._connection.executescript("""
                CREATE TABLE IF NOT EXISTS endpoint_identities (
                    endpoint_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    credential_digest TEXT NOT NULL, created_at REAL NOT NULL,
                    paired_at REAL NOT NULL, last_seen REAL, revoked_at REAL,
                    platform TEXT, worker_version TEXT, capabilities TEXT NOT NULL DEFAULT '[]',
                    last_category TEXT NOT NULL DEFAULT 'paired'
                );
                CREATE TABLE IF NOT EXISTS endpoint_pairing_tokens (
                    digest TEXT PRIMARY KEY, expires_at REAL NOT NULL,
                    created_at REAL NOT NULL, consumed_at REAL
                );
                CREATE TABLE IF NOT EXISTS endpoint_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint_id TEXT,
                    event TEXT NOT NULL, created_at REAL NOT NULL
                );
            """)
            columns = {
                row["name"]
                for row in store._connection.execute("PRAGMA table_info(endpoint_identities)")
            }
            for name, declaration in (
                ("temporary", "INTEGER NOT NULL DEFAULT 0"),
                ("expires_at", "REAL"),
                ("architecture", "TEXT"),
                ("os_release", "TEXT"),
            ):
                if name not in columns:
                    store._connection.execute(
                        f"ALTER TABLE endpoint_identities ADD COLUMN {name} {declaration}"
                    )
            # A temporary identity cannot be revived after control-plane restart.
            store._connection.execute(
                "UPDATE endpoint_identities SET revoked_at = ?, last_category = 'expired' "
                "WHERE temporary = 1 AND revoked_at IS NULL",
                (self.clock(),),
            )

    @staticmethod
    def digest(secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()

    def token(self) -> dict[str, Any]:
        now = self.clock()
        with self.store._lock, self.store._connection:
            connection = self.store._connection
            connection.execute("DELETE FROM endpoint_pairing_tokens WHERE expires_at <= ?", (now,))
            count = connection.execute("SELECT count(*) FROM endpoint_pairing_tokens").fetchone()[0]
            if count >= 16:
                raise ValueError("pairing_capacity")
            token = secrets.token_urlsafe(32)
            connection.execute(
                "INSERT INTO endpoint_pairing_tokens VALUES (?, ?, ?, NULL)",
                (self.digest(token), now + 300, now),
            )
            self._audit(None, "pairing_token_created")
            return {"token": token, "expires_at": now + 300}

    def pair(self, token: str, name: str, *, temporary: bool = False) -> dict[str, str]:
        now = self.clock()
        with self.store._lock, self.store._connection:
            self.failures = [when for when in self.failures if now - when < 60]
            if len(self.failures) >= 10:
                raise ValueError("pairing_rejected")
            row = self.store._connection.execute(
                "SELECT digest, expires_at, consumed_at FROM endpoint_pairing_tokens "
                "WHERE digest = ?",
                (self.digest(token),),
            ).fetchone()
            if (
                row is None
                or not hmac.compare_digest(row["digest"], self.digest(token))
                or row["expires_at"] <= now
                or row["consumed_at"] is not None
            ):
                self.failures.append(now)
                raise ValueError("pairing_rejected")
            if (
                self.store._connection.execute(
                    "SELECT count(*) FROM endpoint_identities"
                ).fetchone()[0]
                >= 256
            ):
                raise ValueError("endpoint_capacity")
            changed = self.store._connection.execute(
                "UPDATE endpoint_pairing_tokens SET consumed_at = ? WHERE digest = ? AND "
                "consumed_at IS NULL",
                (now, row["digest"]),
            ).rowcount
            if changed != 1:
                raise ValueError("pairing_rejected")
            endpoint_id, credential = uuid.uuid4().hex, secrets.token_urlsafe(48)
            self.store._connection.execute(
                "INSERT INTO endpoint_identities (endpoint_id, name, credential_digest, "
                "created_at, paired_at, temporary, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    endpoint_id,
                    name,
                    self.digest(credential),
                    now,
                    now,
                    int(temporary),
                    now + 120 if temporary else None,
                ),
            )
            self._audit(endpoint_id, "paired")
            return {"endpoint_id": endpoint_id, "credential": credential}

    def authenticate(self, endpoint_id: str, credential: str) -> bool:
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT credential_digest, revoked_at, expires_at FROM endpoint_identities "
                "WHERE endpoint_id = ?",
                (endpoint_id,),
            ).fetchone()
            expected = row["credential_digest"] if row else "0" * 64
            valid = hmac.compare_digest(expected, self.digest(credential))
            return bool(
                row
                and valid
                and row["revoked_at"] is None
                and (row["expires_at"] is None or row["expires_at"] > self.clock())
            )

    def list(self) -> list[dict[str, Any]]:
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                "UPDATE endpoint_identities SET revoked_at = ?, last_category = 'expired' "
                "WHERE temporary = 1 AND revoked_at IS NULL AND expires_at <= ?",
                (self.clock(), self.clock()),
            )
            rows = self.store._connection.execute(
                "SELECT endpoint_id, name, created_at, paired_at, last_seen, revoked_at, "
                "platform, worker_version, capabilities, last_category, temporary, expires_at, "
                "architecture, os_release FROM endpoint_identities "
                "ORDER BY created_at LIMIT 256"
            ).fetchall()
        return [{**dict(row), "capabilities": json.loads(row["capabilities"])} for row in rows]

    def get(self, endpoint_id: str) -> dict[str, Any] | None:
        return next((row for row in self.list() if row["endpoint_id"] == endpoint_id), None)

    def update_connection(self, endpoint_id: str, hello: Hello | None, category: str) -> None:
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                "UPDATE endpoint_identities SET last_seen = ?, last_category = ?, "
                "expires_at = CASE WHEN temporary = 1 THEN ? ELSE NULL END "
                "WHERE endpoint_id = ?",
                (self.clock(), category, self.clock() + 120, endpoint_id),
            )
            if hello is not None:
                self.store._connection.execute(
                    "UPDATE endpoint_identities SET platform = ?, worker_version = ?, "
                    "capabilities = ?, architecture = ?, os_release = ? WHERE endpoint_id = ?",
                    (
                        hello.platform,
                        hello.worker_version,
                        json.dumps(hello.capabilities),
                        hello.architecture,
                        hello.os_release,
                        endpoint_id,
                    ),
                )

    def rename(self, endpoint_id: str, name: str) -> None:
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                "UPDATE endpoint_identities SET name = ? WHERE endpoint_id = ?", (name, endpoint_id)
            )
            self._audit(endpoint_id, "renamed")

    def revoke(self, endpoint_id: str) -> None:
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                "UPDATE endpoint_identities SET revoked_at = ? WHERE endpoint_id = ?",
                (self.clock(), endpoint_id),
            )
            self._audit(endpoint_id, "revoked")

    def device_chat(self, endpoint_id: str, principal_id: str, workspace_id: str) -> str:
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT session_id FROM sessions WHERE surface_kind = 'device' AND endpoint_id = ?",
                (endpoint_id,),
            ).fetchone()
            if row:
                return str(row["session_id"])
            return self.store.create_session(principal_id, workspace_id, endpoint_id=endpoint_id)

    def forget(self, endpoint_id: str) -> None:
        with self.store._lock, self.store._connection:
            if (
                self.store._connection.execute(
                    "SELECT 1 FROM requests r JOIN sessions s USING(session_id) "
                    "WHERE s.endpoint_id = ? AND r.status IN ('queued', 'running')",
                    (endpoint_id,),
                ).fetchone()
                is not None
                or self.store._connection.execute(
                    "SELECT 1 FROM scheduled_runs r JOIN scheduled_tasks t USING(task_id) "
                    "JOIN sessions s ON s.session_id = t.execution_session_id "
                    "WHERE s.endpoint_id = ? AND r.status = 'running'",
                    (endpoint_id,),
                ).fetchone()
                is not None
            ):
                raise RuntimeError("active_request")
            rows = self.store._connection.execute(
                "SELECT session_id FROM sessions WHERE endpoint_id = ?", (endpoint_id,)
            ).fetchall()
            for row in rows:
                self.store.delete_session(str(row["session_id"]))
            self.store._connection.execute(
                "DELETE FROM endpoint_audit WHERE endpoint_id = ?", (endpoint_id,)
            )
            self.store._connection.execute(
                "DELETE FROM endpoint_identities WHERE endpoint_id = ?", (endpoint_id,)
            )

    def audit(self, endpoint_id: str, event: str) -> None:
        with self.store._lock, self.store._connection:
            self._audit(endpoint_id, event)

    def _audit(self, endpoint_id: str | None, event: str) -> None:
        self.store._connection.execute(
            "INSERT INTO endpoint_audit (endpoint_id, event, created_at) VALUES (?, ?, ?)",
            (endpoint_id, event, self.clock()),
        )
        self.store._connection.execute(
            "DELETE FROM endpoint_audit WHERE id NOT IN (SELECT id FROM endpoint_audit ORDER "
            "BY id DESC LIMIT 1000)"
        )
