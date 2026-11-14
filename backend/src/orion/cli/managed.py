"""Process-private loopback server for a trusted native host."""

from __future__ import annotations

import hmac
import json
import os
import re
import socket
import sys
import threading
from pathlib import Path
from typing import BinaryIO

import uvicorn
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from orion.access.remote import RemoteAccessConfig
from orion.api.app import create_app
from orion.paths import ORION_HOST, ORION_PORT, PACKAGED_UI_SHELL, log_path

MANAGED_HEADER = b"x-orion-managed-token"


class ManagedAccess:
    def __init__(self, app: ASGIApp, *, token: bytes, remote_enabled: bool = False) -> None:
        self.app = app
        self.token = token
        self.remote_enabled = remote_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            supplied = [value for name, value in scope["headers"] if name.lower() == MANAGED_HEADER]
            if not supplied and self.remote_enabled:
                await self.app(scope, receive, send)
                return
            if len(supplied) != 1 or not hmac.compare_digest(self.token, supplied[0]):
                if scope["type"] == "http":
                    await Response(status_code=401, headers={"Cache-Control": "no-store"})(
                        scope, receive, send
                    )
                else:
                    await send({"type": "websocket.close", "code": 1008})
                return
            scope = {
                **scope,
                **(
                    {"state": {**scope.get("state", {}), "desktop_authenticated": True}}
                    if self.remote_enabled
                    else {}
                ),
                "headers": [
                    (name, value)
                    for name, value in scope["headers"]
                    if name.lower() != MANAGED_HEADER
                ],
            }
        await self.app(scope, receive, send)


class _ManagedServer(uvicorn.Server):
    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        if self.started and sockets:
            port = sockets[0].getsockname()[1]
            print(
                json.dumps({"type": "ready", "origin": f"http://{ORION_HOST}:{port}"}), flush=True
            )


def _watch_parent(pipe: BinaryIO, server: uvicorn.Server) -> None:
    try:
        os.read(pipe.fileno(), 1)
    except OSError:
        pass
    server.should_exit = True


def serve_managed() -> None:
    """Read one host token from stdin. EOF closes the owned server."""
    if sys.stdin.isatty():
        raise SystemExit("Managed Orion requires an owner pipe.")
    pipe = sys.stdin.buffer
    line = pipe.readline(45)
    if not re.fullmatch(rb"[A-Za-z0-9_-]{43}\n", line):
        raise SystemExit("Managed Orion did not receive a valid owner token.")

    os.environ.setdefault("ORION_LOG_PATH", str(log_path()))
    remote = RemoteAccessConfig(False, ORION_HOST)
    frontend = None
    if os.getenv("ORION_DESKTOP_HOST_MODE") == "1":
        remote = RemoteAccessConfig.from_environment()
        if (
            not remote.enabled
            or remote.bind_host != ORION_HOST
            or not (remote.public_origin or "").startswith("https://")
        ):
            raise SystemExit("Desktop Host Mode requires HTTPS and a loopback upstream.")
        frontend = Path(sys.executable).parent.parent / "web"
        if not (frontend / PACKAGED_UI_SHELL).is_file():
            raise SystemExit("Desktop Host Mode requires the packaged web client.")
    app = create_app(remote_config=remote, managed_desktop=True, ui_directory=frontend)
    app.add_middleware(ManagedAccess, token=line[:-1], remote_enabled=remote.enabled)
    with socket.socket() as listener:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((ORION_HOST, ORION_PORT if remote.enabled else 0))
        server = _ManagedServer(
            uvicorn.Config(
                app,
                lifespan="on",
                workers=1,
                proxy_headers=False,
                access_log=False,
                ws_max_size=1_500_000,
                ws_max_queue=4,
                ws_per_message_deflate=False,
                timeout_graceful_shutdown=10,
            )
        )
        threading.Thread(target=_watch_parent, args=(pipe, server), daemon=True).start()
        try:
            server.run(sockets=[listener])
        except KeyboardInterrupt:
            return
        if not server.started:
            raise SystemExit("Managed Orion did not reach readiness.")
