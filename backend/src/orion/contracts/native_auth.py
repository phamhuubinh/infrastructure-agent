"""Owner-native enrollment and token DTOs, separate from worker/provider credentials."""

from typing import Literal

from pydantic import Field, SecretStr

from orion.contracts.application import StrictRequest


class NativeEnrollmentInput(StrictRequest):
    code: SecretStr = Field(min_length=32, max_length=128, repr=False)
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")
    platform: Literal["windows", "linux", "android", "ios"]


class NativeRefreshInput(StrictRequest):
    refresh_token: SecretStr = Field(min_length=32, max_length=128, repr=False)


class NativeEnrollmentCode(StrictRequest):
    code: str = Field(repr=False)
    expires_at: int


class NativeTokenPair(StrictRequest):
    session_id: str
    token_type: Literal["Bearer"] = "Bearer"
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    access_expires_at: int
    refresh_expires_at: int


class NativeSessionView(StrictRequest):
    session_id: str
    name: str
    platform: str
    created_at: int
    expires_at: int
    revoked_at: int | None
