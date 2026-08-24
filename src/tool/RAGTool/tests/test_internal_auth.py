from __future__ import annotations

import asyncio
from dataclasses import replace

from app import main
from starlette.requests import Request
from starlette.responses import Response


def test_non_health_routes_require_exact_internal_token(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "_config",
        replace(main._config, internal_token="root-to-rag-test-token"),
    )
    async def call(path: str, token: str = "") -> Response:
        headers = [(b"x-orion-rag-token", token.encode())] if token else []
        request = Request(
            {"type": "http", "method": "GET", "path": path, "headers": headers}
        )

        async def accepted(_: Request) -> Response:
            return Response(status_code=204)

        return await main.require_internal_token(request, accepted)

    assert asyncio.run(call("/health")).status_code == 204
    assert asyncio.run(call("/projects")).status_code == 403
    assert asyncio.run(call("/projects", "wrong-token")).status_code == 403
    assert asyncio.run(call("/projects", "root-to-rag-test-token")).status_code == 204
