from __future__ import annotations

import os
import secrets

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.shared.logger import info as _info


def _get_api_key() -> str | None:
    return os.environ.get("ORION_API_KEY")


def _is_public_path(path: str) -> bool:
    return path == "/api/health"


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
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

                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )
            _info(
                "audit",
                event="auth_success",
                path=request.url.path,
                client=str(request.client.host) if request.client else "unknown",
            )
        return await call_next(request)
