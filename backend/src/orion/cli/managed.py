"""Process-private loopback server for a trusted native host."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import socket
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

import uvicorn
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from orion.access.remote import RemoteAccessConfig
from orion.api.app import create_app
from orion.paths import ORION_HOST, ORION_PORT, PACKAGED_UI_SHELL, data_directory, log_path

MANAGED_HEADER = b"x-orion-managed-token"
UPDATE_PATH = "/api/internal/prepare-update"
UPDATE_HEADER = b"x-orion-local-maintenance"


class ManagedAccess:
    def __init__(
        self,
        app: ASGIApp,
        *,
        token: bytes,
        remote_enabled: bool = False,
        work_active: Callable[[], bool] | None = None,
        pause_scheduler: Callable[[bool], bool] | None = None,
        update_commit: Path | None = None,
    ) -> None:
        self.app = app
        self.token = token
        self.remote_enabled = remote_enabled
        self.work_active = work_active
        self.pause_scheduler = pause_scheduler
        self.update_commit = update_commit
        self.in_flight = 0
        self.preparing = False

    def _resume(self) -> None:
        self.preparing = False
        if self.pause_scheduler:
            self.pause_scheduler(False)

    async def _serve(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.update_commit is not None and self.update_commit.is_file():
            self.update_commit = None
            self._resume()
        local_health = (
            scope["type"] == "http"
            and scope["method"] == "GET"
            and scope["path"] == "/api/health"
            and scope.get("state", {}).get("desktop_authenticated") is True
        )
        if self.preparing or (self.update_commit is not None and not local_health):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1013})
            else:
                await Response(status_code=503, headers={"Retry-After": "15"})(scope, receive, send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        self.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            supplied = [value for name, value in scope["headers"] if name.lower() == MANAGED_HEADER]
            trusted = len(supplied) == 1 and hmac.compare_digest(self.token, supplied[0])
            if scope["type"] == "http" and scope["path"] == UPDATE_PATH:
                local = [value for name, value in scope["headers"] if name.lower() == UPDATE_HEADER]
                if not trusted or scope["method"] != "POST" or local != [b"1"]:
                    status = 403
                elif (
                    self.preparing
                    or self.update_commit is not None
                    or self.in_flight
                    or not self.work_active
                    or not self.pause_scheduler
                    or self.work_active()
                    or not self.pause_scheduler(True)
                ):
                    status = 409
                else:
                    self.preparing = True
                    asyncio.get_running_loop().call_later(30, self._resume)
                    status = 204
                await Response(status_code=status, headers={"Cache-Control": "no-store"})(
                    scope, receive, send
                )
                return
            if not supplied and self.remote_enabled:
                await self._serve(scope, receive, send)
                return
            if not trusted:
                if scope["type"] == "http":
                    await Response(status_code=401, headers={"Cache-Control": "no-store"})(
                        scope, receive, send
                    )
                else:
                    await send({"type": "websocket.close", "code": 1008})
                return
            scope = {
                **scope,
                "state": {**scope.get("state", {}), "desktop_authenticated": True},
                "headers": [
                    (name, value)
                    for name, value in scope["headers"]
                    if name.lower() != MANAGED_HEADER
                ],
            }
        if scope["type"] in {"http", "websocket"}:
            await self._serve(scope, receive, send)
        else:
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

    probe = os.getenv("ORION_STARTUP_PROBE") == "1"
    start = time.perf_counter()

    def mark(phase: str) -> None:
        if probe:
            with (data_directory() / "backend-startup.jsonl").open("a", encoding="utf-8") as log:
                log.write(
                    json.dumps(
                        {
                            "phase": phase,
                            "elapsed_ms": round((time.perf_counter() - start) * 1000),
                        }
                    )
                    + "\n"
                )

    mark("owner_pipe_validated")
    os.environ.setdefault("ORION_LOG_PATH", str(log_path()))
    remote = RemoteAccessConfig(False, ORION_HOST)
    frontend = None
    if os.getenv("ORION_DESKTOP_HOST_MODE") == "1":
        remote = RemoteAccessConfig.from_environment(owner_credentials=True)
        if (
            not remote.enabled
            or remote.bind_host != ORION_HOST
            or not (remote.public_origin or "").startswith("https://")
        ):
            raise SystemExit("Desktop Host Mode requires HTTPS and a loopback upstream.")
        frontend = Path(sys.executable).parent.parent / "web"
        if not (frontend / PACKAGED_UI_SHELL).is_file():
            raise SystemExit("Desktop Host Mode requires the packaged web client.")
    commit_path = os.getenv("ORION_UPDATE_COMMIT")
    app = create_app(
        remote_config=remote,
        managed_desktop=True,
        ui_directory=frontend,
        update_pending=bool(commit_path),
    )
    mark("application_constructed")
    app.add_middleware(
        ManagedAccess,
        token=line[:-1],
        remote_enabled=remote.enabled,
        work_active=lambda: app.state.application.store.update_work_active(),
        pause_scheduler=lambda paused: app.state.application.scheduler_engine.pause_for_update(
            paused
        ),
        update_commit=Path(commit_path) if commit_path else None,
    )
    with socket.socket() as listener:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((ORION_HOST, ORION_PORT if remote.enabled else 0))
        mark("listener_bound")
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
