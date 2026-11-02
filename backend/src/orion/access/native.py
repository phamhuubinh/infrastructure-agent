"""Opaque native owner access with single-use enrollment and refresh replay revocation."""

from __future__ import annotations

import hashlib
import math
import re
import secrets
import time
from collections.abc import Callable

from orion.access import Principal
from orion.contracts.native_auth import (
    NativeEnrollmentCode,
    NativeEnrollmentInput,
    NativeSessionView,
    NativeTokenPair,
)
from orion.persistence.sqlite import SQLiteStore

ACCESS_SECONDS = 900
ENROLLMENT_SECONDS = 300
SESSION_SECONDS = 30 * 24 * 60 * 60


class NativeAuthError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__("Native access unavailable: " + category)


class NativeAuthService:
    def __init__(self, store: SQLiteStore, clock: Callable[[], float] = time.time) -> None:
        self.store, self.clock = store, clock

    def _now(self) -> int:
        now = self.clock()
        if not math.isfinite(now) or now < 0:
            raise NativeAuthError("clock")
        return int(now)

    @staticmethod
    def _token(kind: str) -> str:
        return "orion_" + kind + "_" + secrets.token_urlsafe(32)

    @staticmethod
    def _digest(token: str, kind: str) -> str:
        if not re.fullmatch("orion_" + kind + r"_[A-Za-z0-9_-]{43}", token):
            raise NativeAuthError("invalid_credential")
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def create_enrollment(self, owner: Principal) -> NativeEnrollmentCode:
        now, code = self._now(), self._token("enroll")
        if not self.store.create_native_enrollment(
            self._digest(code, "enroll"),
            owner.principal_id,
            owner.workspace_id,
            now + ENROLLMENT_SECONDS,
            now,
        ):
            raise NativeAuthError("enrollment_capacity")
        return NativeEnrollmentCode(code=code, expires_at=now + ENROLLMENT_SECONDS)

    def enroll(self, values: NativeEnrollmentInput) -> NativeTokenPair:
        now = self._now()
        access, refresh = self._token("access"), self._token("refresh")
        row = self.store.consume_native_enrollment(
            self._digest(values.code.get_secret_value(), "enroll"),
            values.name,
            values.platform,
            self._digest(access, "access"),
            self._digest(refresh, "refresh"),
            now,
            now + ACCESS_SECONDS,
            now + SESSION_SECONDS,
        )
        if row is None:
            raise NativeAuthError("invalid_enrollment")
        return NativeTokenPair(
            session_id=row["session_id"],
            access_token=access,
            refresh_token=refresh,
            access_expires_at=row["access_expires_at"],
            refresh_expires_at=row["expires_at"],
        )

    def refresh(self, token: str) -> NativeTokenPair:
        now = self._now()
        access, refresh = self._token("access"), self._token("refresh")
        status, row = self.store.rotate_native_refresh(
            self._digest(token, "refresh"),
            self._digest(access, "access"),
            self._digest(refresh, "refresh"),
            now,
            now + ACCESS_SECONDS,
        )
        if row is None:
            raise NativeAuthError(status)
        return NativeTokenPair(
            session_id=row["session_id"],
            access_token=access,
            refresh_token=refresh,
            access_expires_at=row["access_expires_at"],
            refresh_expires_at=row["expires_at"],
        )

    def authenticate(self, token: str) -> tuple[Principal, str] | None:
        try:
            row = self.store.native_access_identity(self._digest(token, "access"), self._now())
        except NativeAuthError:
            return None
        if row is None:
            return None
        return Principal(row["principal_id"], row["workspace_id"]), row["session_id"]

    def sessions(self, owner: Principal) -> list[NativeSessionView]:
        return [
            NativeSessionView.model_validate(row)
            for row in self.store.native_owner_sessions(owner.principal_id, owner.workspace_id)
        ]

    def session_active(self, session_id: str, owner: Principal) -> bool:
        return self.store.native_session_active(
            session_id, owner.principal_id, owner.workspace_id, self._now()
        )

    def revoke(self, session_id: str, owner: Principal) -> bool:
        return self.store.revoke_native_session(
            session_id, owner.principal_id, owner.workspace_id, self._now()
        )
