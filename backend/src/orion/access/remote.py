"""The optional single-owner HTTP authentication boundary."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from orion.paths import ORION_HOST

COOKIE_NAME = "orion_session"
SESSION_SECONDS = 12 * 60 * 60
MAX_SESSIONS = 32
_HASHER = PasswordHasher(type=Type.ID)


@dataclass(frozen=True)
class RemoteAccessConfig:
    enabled: bool
    bind_host: str
    public_origin: str | None = None
    password_hash: str | None = None

    @classmethod
    def from_environment(cls) -> RemoteAccessConfig:
        mode = os.getenv("ORION_REMOTE_ACCESS")
        bind = os.getenv("ORION_BIND_HOST", ORION_HOST)
        origin = os.getenv("ORION_PUBLIC_ORIGIN")
        password_hash = os.getenv("ORION_AUTH_PASSWORD_HASH")
        if mode not in (None, "0", "1"):
            raise ValueError("ORION_REMOTE_ACCESS must be 1 or 0.")
        try:
            address = ipaddress.ip_address(bind)
        except ValueError:
            raise ValueError("ORION_BIND_HOST must be a numeric IP address.") from None
        if not mode or mode == "0":
            if not address.is_loopback or origin or password_hash:
                raise ValueError("Remote access configuration is incomplete or disabled.")
            return cls(False, bind)
        if not origin or not password_hash:
            raise ValueError("Remote access requires a public origin and encoded password hash.")
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("ORION_PUBLIC_ORIGIN must be one canonical origin.")
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("ORION_PUBLIC_ORIGIN has an invalid port.") from None
        host = parsed.hostname
        assert host is not None
        try:
            host_address = ipaddress.ip_address(host)
        except ValueError:
            host_address = None
            if all(label.isdigit() for label in host.split(".")):
                raise ValueError("ORION_PUBLIC_ORIGIN has an invalid IP address.") from None
            if not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) for label in host.split(".")
            ):
                raise ValueError("ORION_PUBLIC_ORIGIN has an invalid host.") from None
        if host_address is not None and str(host_address) != host:
            raise ValueError("ORION_PUBLIC_ORIGIN must use a canonical IP address.")
        if port in (0, 80 if parsed.scheme == "http" else 443):
            raise ValueError("ORION_PUBLIC_ORIGIN must omit its default port.")
        canonical_host = f"[{host}]" if isinstance(host_address, ipaddress.IPv6Address) else host
        canonical_origin = f"{parsed.scheme}://{canonical_host}"
        if port is not None:
            canonical_origin += f":{port}"
        if origin != canonical_origin:
            raise ValueError("ORION_PUBLIC_ORIGIN must be one canonical origin.")
        if parsed.scheme == "http":
            if not address.is_loopback or host_address is None or not host_address.is_loopback:
                raise ValueError("Remote public origin must use HTTPS.")
        if not password_hash.startswith("$argon2id$"):
            raise ValueError("ORION_AUTH_PASSWORD_HASH must be an Argon2id encoded hash.")
        try:
            _HASHER.verify(password_hash, "validation-only-password")
        except VerifyMismatchError:
            pass
        except (InvalidHashError, VerificationError):
            raise ValueError("ORION_AUTH_PASSWORD_HASH is invalid.") from None
        return cls(True, bind, origin, password_hash)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")
    return _HASHER.hash(password)


class BrowserSessions:
    """Bounded process-local tokens; only SHA-256 digests are retained."""

    def __init__(self, password_hash: str, *, clock: Callable[[], float] = time.time) -> None:
        self._password_hash = password_hash
        self._clock = clock
        self._tokens: dict[str, float] = {}
        self._failures: list[float] = []
        self._lock = threading.Lock()

    def login(self, password: str) -> tuple[str, float] | None:
        with self._lock:
            now = self._clock()
            self._failures = [when for when in self._failures if now - when < 60]
            if len(self._failures) >= 10:
                return None
            try:
                verified = bool(_HASHER.verify(self._password_hash, password))
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                verified = False
            if not verified:
                self._failures.append(now)
                return None
            self._failures.clear()
            self._prune(now)
            if len(self._tokens) >= MAX_SESSIONS:
                self._tokens.pop(min(self._tokens, key=self._tokens.get))  # type: ignore[arg-type]
            token = secrets.token_urlsafe(32)
            expiry = now + SESSION_SECONDS
            self._tokens[self._digest(token)] = expiry
            return token, expiry

    def expiry(self, token: str | None) -> float | None:
        if not token:
            return None
        with self._lock:
            self._prune(self._clock())
            candidate = self._digest(token)
            for digest, expiry in self._tokens.items():
                if hmac.compare_digest(digest, candidate):
                    return expiry
            return None

    def logout(self, token: str | None) -> None:
        if token:
            with self._lock:
                candidate = self._digest(token)
                for digest in self._tokens:
                    if hmac.compare_digest(digest, candidate):
                        del self._tokens[digest]
                        break

    def _prune(self, now: float) -> None:
        self._tokens = {digest: expiry for digest, expiry in self._tokens.items() if expiry > now}

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
