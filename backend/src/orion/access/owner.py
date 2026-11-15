"""Single desktop owner credentials, with persistent TOTP replay protection."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from orion.persistence.sqlite import SQLiteStore

_HASHER = PasswordHasher(type=Type.ID)
_SETUP_SECONDS = 300
_ATTEMPT_SECONDS = 60
_MAX_ATTEMPTS = 10


class OwnerAuthError(ValueError):
    """Only fixed failure categories cross the HTTP boundary."""


@dataclass(repr=False)
class _Setup:
    setup_id: str
    password_hash: str
    secret: bytes
    expires_at: float
    rotation: bool
    attempts: int = field(default=0)


def totp_code(secret: bytes, counter: int) -> str:
    digest = hmac.digest(secret, counter.to_bytes(8, "big"), "sha1")
    offset = digest[-1] & 15
    truncate = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFF_FFFF
    return f"{truncate % 1_000_000:06d}"


def _replay_counter(secret: bytes, code: str, last_counter: int, now: float) -> int | None:
    if not (len(code) == 6 and code.isascii() and code.isdigit()):
        return None
    current = int(now // 30)
    for counter in (current, current - 1):
        if (
            counter >= 0
            and counter > last_counter
            and hmac.compare_digest(totp_code(secret, counter), code)
        ):
            return counter
    return None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OwnerAuth:
    def __init__(
        self,
        store: SQLiteStore,
        *,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store, self.clock, self.monotonic = store, clock, monotonic
        self._lock = threading.Lock()
        self._failures: list[float] = []
        self._setup: _Setup | None = None
        with store._lock, store._connection:
            store._connection.execute(
                "CREATE TABLE IF NOT EXISTS desktop_owner ("
                "id INTEGER PRIMARY KEY CHECK(id=1), password_hash TEXT NOT NULL,"
                "totp_secret BLOB NOT NULL, last_counter INTEGER NOT NULL,"
                "recovery_digests TEXT NOT NULL)"
            )

    @property
    def configured(self) -> bool:
        with self.store._lock:
            return (
                self.store._connection.execute("SELECT 1 FROM desktop_owner WHERE id=1").fetchone()
                is not None
            )

    def _verify(self, password: str, code: str) -> bool:
        # Caller holds the service lock through the authenticated operation.
        now = self.monotonic()
        self._failures = [item for item in self._failures if now - item < _ATTEMPT_SECONDS]
        if len(self._failures) >= _MAX_ATTEMPTS:
            return False
        store = self.store
        with store._lock:
            row = store._connection.execute("SELECT * FROM desktop_owner WHERE id=1").fetchone()
        if row is not None:
            try:
                valid_password: bool = _HASHER.verify(row["password_hash"], password)
            except (InvalidHashError, VerificationError, UnicodeError):
                valid_password = False
            if valid_password:
                with store._lock, store._connection:
                    counter = _replay_counter(
                        row["totp_secret"], code, row["last_counter"], self.clock()
                    )
                    if counter is not None:
                        store._connection.execute(
                            "UPDATE desktop_owner SET last_counter=? WHERE id=1", (counter,)
                        )
                        return True
                    if len(code) == 24 and code.isascii():
                        recovery = json.loads(row["recovery_digests"])
                        digest = _digest(code)
                        if any(hmac.compare_digest(item, digest) for item in recovery):
                            recovery.remove(digest)
                            store._connection.execute(
                                "UPDATE desktop_owner SET recovery_digests=? WHERE id=1",
                                (json.dumps(recovery),),
                            )
                            return True
        self._failures.append(now)
        return False

    def verify(self, password: str, code: str) -> bool:
        with self._lock:
            return self._verify(password, code)

    def with_credentials[T](self, password: str, code: str, action: Callable[[], T]) -> T:
        with self._lock:
            if not self._verify(password, code):
                raise OwnerAuthError("invalid_credentials")
            return action()

    def _start(self, password_hash: str, *, rotation: bool) -> tuple[str, str]:
        secret = secrets.token_bytes(20)
        setup_id = secrets.token_urlsafe(24)
        self._setup = _Setup(
            setup_id, password_hash, secret, self.monotonic() + _SETUP_SECONDS, rotation
        )
        params = urlencode(
            {
                "secret": base64.b32encode(secret).decode("ascii"),
                "issuer": "Orion",
                "algorithm": "SHA1",
                "digits": 6,
                "period": 30,
            }
        )
        return setup_id, "otpauth://totp/Orion:Owner?" + params

    def start_setup(self, password: str) -> tuple[str, str]:
        with self._lock:
            if self.configured:
                raise OwnerAuthError("already_configured")
            return self._start(_HASHER.hash(password), rotation=False)

    def start_rotation(self, password: str, code: str) -> tuple[str, str]:
        with self._lock:
            if not self._verify(password, code):
                raise OwnerAuthError("invalid_credentials")
            with self.store._lock:
                password_hash = self.store._connection.execute(
                    "SELECT password_hash FROM desktop_owner WHERE id=1"
                ).fetchone()[0]
            return self._start(password_hash, rotation=True)

    def confirm_setup(self, setup_id: str, code: str, *, rotation: bool) -> tuple[str, ...]:
        with self._lock:
            setup = self._setup
            if (
                setup is None
                or self.monotonic() >= setup.expires_at
                or setup.attempts >= _MAX_ATTEMPTS
                or rotation != setup.rotation
                or not hmac.compare_digest(setup.setup_id, setup_id)
            ):
                raise OwnerAuthError("setup_unavailable")
            counter = _replay_counter(setup.secret, code, -1, self.clock())
            if counter is None:
                setup.attempts += 1
                raise OwnerAuthError("invalid_credentials")
            recovery = tuple(secrets.token_urlsafe(18) for _ in range(10))
            with self.store._lock, self.store._connection:
                self.store._connection.execute(
                    "INSERT INTO desktop_owner VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "password_hash=excluded.password_hash, totp_secret=excluded.totp_secret, "
                    "last_counter=excluded.last_counter, "
                    "recovery_digests=excluded.recovery_digests",
                    (
                        setup.password_hash,
                        setup.secret,
                        counter,
                        json.dumps([_digest(item) for item in recovery]),
                    ),
                )
                self._revoke_native()
            self._setup = None
            return recovery

    def change_password(self, password: str, code: str, new_password: str) -> None:
        with self._lock:
            if not self._verify(password, code):
                raise OwnerAuthError("invalid_credentials")
            password_hash = _HASHER.hash(new_password)
            with self.store._lock, self.store._connection:
                self.store._connection.execute(
                    "UPDATE desktop_owner SET password_hash=? WHERE id=1", (password_hash,)
                )
                self._revoke_native()
            self._setup = None

    def revoke_all(self, password: str, code: str) -> None:
        with self._lock:
            if not self._verify(password, code):
                raise OwnerAuthError("invalid_credentials")
            with self.store._lock, self.store._connection:
                self._revoke_native()
            self._setup = None

    def _revoke_native(self) -> None:
        connection = self.store._connection
        connection.execute(
            "UPDATE native_sessions SET revoked_at=? WHERE revoked_at IS NULL", (int(self.clock()),)
        )
        connection.execute("DELETE FROM native_enrollments")
