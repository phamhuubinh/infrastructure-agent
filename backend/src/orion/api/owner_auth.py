"""Trusted Desktop-only owner setup and credential management."""

import asyncio
import re
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import Field, SecretStr, ValidationInfo, field_validator

from orion.access.owner import OwnerAuth, OwnerAuthError
from orion.access.remote import BrowserSessions
from orion.api.native_auth import _credentials
from orion.api.schema import request_body_schema
from orion.contracts.application import StrictRequest

OWNER_DESKTOP_ROUTES = {
    ("GET", "/api/auth/owner"),
    ("POST", "/api/auth/owner/setup/start"),
    ("POST", "/api/auth/owner/setup/confirm"),
    ("POST", "/api/auth/owner/password"),
    ("POST", "/api/auth/owner/totp/start"),
    ("POST", "/api/auth/owner/totp/confirm"),
    ("POST", "/api/auth/owner/revoke-all"),
}


class _Start(StrictRequest):
    password: SecretStr = Field(min_length=12, max_length=1024)


class _Credentials(StrictRequest):
    password: SecretStr = Field(min_length=1, max_length=1024)
    code: SecretStr = Field(min_length=1, max_length=64)


class _Confirm(StrictRequest):
    setup_id: SecretStr = Field(min_length=32, max_length=32)
    code: SecretStr = Field(min_length=6, max_length=6)

    @field_validator("setup_id", "code")
    @classmethod
    def ascii_credential(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        pattern = r"[A-Za-z0-9_-]+" if info.field_name == "setup_id" else r"[0-9]+"
        if not re.fullmatch(pattern, value.get_secret_value()):
            raise ValueError("Invalid setup credential")
        return value


class _Password(StrictRequest):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    code: SecretStr = Field(min_length=1, max_length=64)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


def install_owner_auth_routes(
    app: FastAPI, owner: OwnerAuth | None, sessions: BrowserSessions | None
) -> None:
    def trusted(request: Request, response: Response) -> OwnerAuth:
        response.headers["Cache-Control"] = "no-store"
        if owner is None:
            raise HTTPException(404, "Owner setup is available in Orion Desktop")
        if getattr(request.state, "desktop_authenticated", False) is not True:
            raise HTTPException(403, "Trusted Orion Desktop is required")
        return owner

    async def run[T](
        action: Callable[..., T], *args: Any, revoke_browser: bool = False, **kwargs: Any
    ) -> T:
        def execute() -> T:
            result = action(*args, **kwargs)
            if revoke_browser and sessions is not None:
                sessions.revoke_all()
            return result

        try:
            return await asyncio.to_thread(execute)
        except OwnerAuthError as error:
            if str(error) in {"already_configured", "setup_unavailable"}:
                raise HTTPException(409, "Owner setup is unavailable or expired") from None
            raise HTTPException(401, "Invalid owner credentials") from None

    @app.get("/api/auth/owner")
    async def status(request: Request, response: Response) -> dict[str, bool]:
        return {"configured": trusted(request, response).configured}

    @app.post("/api/auth/owner/setup/start", openapi_extra=request_body_schema(_Start))
    async def start(request: Request, response: Response) -> dict[str, str]:
        auth = trusted(request, response)
        inputs = await _credentials(request, _Start, max_bytes=8192)
        setup_id, uri = await run(auth.start_setup, inputs.password.get_secret_value())
        return {"setup_id": setup_id, "otpauth_uri": uri}

    async def finish(
        request: Request, response: Response, *, rotation: bool
    ) -> dict[str, tuple[str, ...]]:
        auth = trusted(request, response)
        inputs = await _credentials(request, _Confirm)
        codes = await run(
            auth.confirm_setup,
            inputs.setup_id.get_secret_value(),
            inputs.code.get_secret_value(),
            rotation=rotation,
            revoke_browser=True,
        )
        return {"recovery_codes": codes}

    @app.post("/api/auth/owner/setup/confirm", openapi_extra=request_body_schema(_Confirm))
    async def confirm(request: Request, response: Response) -> dict[str, tuple[str, ...]]:
        return await finish(request, response, rotation=False)

    @app.post("/api/auth/owner/password", openapi_extra=request_body_schema(_Password))
    async def change_password(request: Request, response: Response) -> dict[str, str]:
        auth = trusted(request, response)
        inputs = await _credentials(request, _Password, max_bytes=16384)
        await run(
            auth.change_password,
            inputs.current_password.get_secret_value(),
            inputs.code.get_secret_value(),
            inputs.new_password.get_secret_value(),
            revoke_browser=True,
        )
        return {"status": "updated"}

    @app.post("/api/auth/owner/totp/start", openapi_extra=request_body_schema(_Credentials))
    async def rotate(request: Request, response: Response) -> dict[str, str]:
        auth = trusted(request, response)
        inputs = await _credentials(request, _Credentials, max_bytes=8192)
        setup_id, uri = await run(
            auth.start_rotation,
            inputs.password.get_secret_value(),
            inputs.code.get_secret_value(),
        )
        return {"setup_id": setup_id, "otpauth_uri": uri}

    @app.post("/api/auth/owner/totp/confirm", openapi_extra=request_body_schema(_Confirm))
    async def confirm_rotation(request: Request, response: Response) -> dict[str, tuple[str, ...]]:
        return await finish(request, response, rotation=True)

    @app.post("/api/auth/owner/revoke-all", openapi_extra=request_body_schema(_Credentials))
    async def revoke_all(request: Request, response: Response) -> dict[str, str]:
        auth = trusted(request, response)
        inputs = await _credentials(request, _Credentials, max_bytes=8192)
        await run(
            auth.revoke_all,
            inputs.password.get_secret_value(),
            inputs.code.get_secret_value(),
            revoke_browser=True,
        )
        return {"status": "revoked"}
