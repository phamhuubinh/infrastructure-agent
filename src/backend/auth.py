from __future__ import annotations

import os
import secrets

from fastapi import Request

from src.shared.logger import info as _info


def _get_api_key() -> str | None:
    value = os.environ.get("ORION_API_KEY", "").strip()
    return value or None


def _is_public_path(path: str) -> bool:
    return path == "/api/health"


class APIKeyMiddleware:
    """Small ASGI auth middleware; avoids BaseHTTP task/stream deadlocks."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        api_key = _get_api_key()
        if api_key is not None and not _is_public_path(request.url.path):
            auth_header = request.headers.get("Authorization")
            x_api_key = request.headers.get("X-API-Key")
            token: str | None = None
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ")
            elif x_api_key:
                token = x_api_key
            if token is None or not secrets.compare_digest(token, api_key):
                _info(
                    "audit",
                    event="auth_failure",
                    path=request.url.path,
                    client=str(request.client.host) if request.client else "unknown",
                    reason="missing_or_invalid" if token is None else "invalid_key",
                )
                from fastapi.responses import JSONResponse

                await JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )(scope, receive, send)
                return
            _info(
                "audit",
                event="auth_success",
                path=request.url.path,
                client=str(request.client.host) if request.client else "unknown",
            )
        await self.app(scope, receive, send)
