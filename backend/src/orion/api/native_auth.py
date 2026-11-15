"""Explicit JSON enrollment/refresh and protected owner-native session administration."""

import asyncio
import json

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ValidationError

from orion.access import LocalAccessAdapter
from orion.access.native import NativeAuthError, NativeAuthService
from orion.access.owner import OwnerAuth, OwnerAuthError
from orion.api.schema import request_body_schema
from orion.contracts.native_auth import (
    NativeEnrollmentCode,
    NativeEnrollmentInput,
    NativeRefreshInput,
    NativeSessionView,
    NativeTokenPair,
)

NATIVE_PUBLIC_ROUTES = {
    ("POST", "/api/auth/native/enroll"),
    ("POST", "/api/auth/native/refresh"),
}
NATIVE_OWNER_ROUTES = {
    ("POST", "/api/auth/native/enrollment-codes"),
    ("GET", "/api/auth/native/sessions"),
    ("POST", "/api/auth/native/sessions/{native_session_id}/revoke"),
    ("POST", "/api/auth/native/logout"),
}


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate credential field")
        value[key] = item
    return value


async def _credentials[T: BaseModel](
    request: Request, model: type[T], *, max_bytes: int = 2048
) -> T:
    if request.headers.get("content-type", "").partition(";")[0].lower() != "application/json":
        raise HTTPException(415, "Native credentials require application/json")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_bytes:
            raise HTTPException(413, "Native credential request is too large")
        body.extend(chunk)
    try:
        return model.model_validate(json.loads(body, object_pairs_hook=_unique))
    except (ValueError, UnicodeError, RecursionError, ValidationError):
        raise HTTPException(422, "Invalid native credential request") from None


def install_native_auth_routes(
    app: FastAPI,
    service: NativeAuthService,
    access: LocalAccessAdapter,
    *,
    owner: OwnerAuth | None = None,
) -> None:
    @app.post("/api/auth/native/enrollment-codes", response_model=NativeEnrollmentCode)
    async def create_enrollment(request: Request, response: Response) -> NativeEnrollmentCode:
        response.headers["Cache-Control"] = "no-store"
        if owner is not None and (
            not getattr(request.state, "desktop_authenticated", False) or not owner.configured
        ):
            raise HTTPException(403, "Configured Orion Desktop owner is required")
        try:
            return service.create_enrollment(access.current_principal())
        except NativeAuthError:
            raise HTTPException(429, "Native enrollment unavailable") from None

    @app.post(
        "/api/auth/native/enroll",
        response_model=NativeTokenPair,
        openapi_extra=request_body_schema(NativeEnrollmentInput),
    )
    async def enroll(request: Request, response: Response) -> NativeTokenPair:
        response.headers["Cache-Control"] = "no-store"
        values = await _credentials(
            request, NativeEnrollmentInput, max_bytes=8192 if owner is not None else 2048
        )
        try:
            if owner is None:
                return service.enroll(values)
            if values.password is None or values.totp_code is None:
                raise OwnerAuthError("invalid_credentials")
            return await asyncio.to_thread(
                owner.with_credentials,
                values.password.get_secret_value(),
                values.totp_code.get_secret_value(),
                lambda: service.enroll(values),
            )
        except (NativeAuthError, OwnerAuthError):
            raise HTTPException(401, "Invalid native enrollment") from None

    @app.post(
        "/api/auth/native/refresh",
        response_model=NativeTokenPair,
        openapi_extra=request_body_schema(NativeRefreshInput),
    )
    async def refresh(request: Request, response: Response) -> NativeTokenPair:
        response.headers["Cache-Control"] = "no-store"
        values = await _credentials(request, NativeRefreshInput)
        if owner is not None and not owner.configured:
            raise HTTPException(401, "Invalid native refresh credential")
        try:
            return service.refresh(values.refresh_token.get_secret_value())
        except NativeAuthError:
            raise HTTPException(401, "Invalid native refresh credential") from None

    @app.get("/api/auth/native/sessions", response_model=list[NativeSessionView])
    async def sessions(response: Response) -> list[NativeSessionView]:
        response.headers["Cache-Control"] = "no-store"
        return service.sessions(access.current_principal())

    @app.post("/api/auth/native/sessions/{native_session_id}/revoke")
    async def revoke(native_session_id: str) -> dict[str, str]:
        if not service.revoke(native_session_id, access.current_principal()):
            raise HTTPException(404, "Native session not found")
        return {"status": "revoked"}

    @app.post("/api/auth/native/logout")
    async def logout(request: Request) -> dict[str, str]:
        native_session = getattr(request.state, "native_session_id", None)
        if not isinstance(native_session, str):
            raise HTTPException(409, "A native session is required")
        service.revoke(native_session, access.current_principal())
        return {"status": "revoked"}
