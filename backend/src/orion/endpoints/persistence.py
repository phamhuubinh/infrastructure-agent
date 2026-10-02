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

    def pair(self, token: str, name: str) -> dict[str, str]:
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
                "created_at, paired_at) VALUES (?, ?, ?, ?, ?)",
                (endpoint_id, name, self.digest(credential), now, now),
            )
            self._audit(endpoint_id, "paired")
            return {"endpoint_id": endpoint_id, "credential": credential}

    def authenticate(self, endpoint_id: str, credential: str) -> bool:
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT credential_digest, revoked_at FROM endpoint_identities "
                "WHERE endpoint_id = ?",
                (endpoint_id,),
            ).fetchone()
            expected = row["credential_digest"] if row else "0" * 64
            valid = hmac.compare_digest(expected, self.digest(credential))
            return bool(row and valid and row["revoked_at"] is None)

    def list(self) -> list[dict[str, Any]]:
        with self.store._lock:
            rows = self.store._connection.execute(
                "SELECT endpoint_id, name, created_at, paired_at, last_seen, revoked_at, "
                "platform, worker_version, capabilities, last_category FROM endpoint_identities "
                "ORDER BY created_at LIMIT 256"
            ).fetchall()
        return [{**dict(row), "capabilities": json.loads(row["capabilities"])} for row in rows]

    def get(self, endpoint_id: str) -> dict[str, Any] | None:
        return next((row for row in self.list() if row["endpoint_id"] == endpoint_id), None)

    def update_connection(self, endpoint_id: str, hello: Hello | None, category: str) -> None:
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                "UPDATE endpoint_identities SET last_seen = ?, last_category = ? "
                "WHERE endpoint_id = ?",
                (self.clock(), category, endpoint_id),
            )
            if hello is not None:
                self.store._connection.execute(
                    "UPDATE endpoint_identities SET platform = ?, worker_version = ?, "
                    "capabilities = ? WHERE endpoint_id = ?",
                    (
                        hello.platform,
                        hello.worker_version,
                        json.dumps(hello.capabilities),
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
