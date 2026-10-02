"""Distinct owner, pairing-token and device boundaries for remote endpoints."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import re
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import Response, StreamingResponse
from pydantic import Field

from orion.access.remote import COOKIE_NAME, BrowserSessions, RemoteAccessConfig
from orion.contracts import RuntimeScope
from orion.endpoints.manager import EndpointError, EndpointManager
from orion_endpoint.protocol import CHUNK_SIZE, MAX_TRANSFER, OPERATIONS, Capture, Strict

PAIRING_API_ROUTES = {("POST", "/api/endpoints/pair")}
DEVICE_API_ROUTES = {("POST", "/api/endpoints/{endpoint_id}/end")}
DEVICE_WS_ROUTES = {("WEBSOCKET", "/api/endpoints/{endpoint_id}/worker")}
ENDPOINT_OWNER_ROUTES = {
    ("GET", "/api/endpoints/artifacts"),
    ("POST", "/api/endpoints/{endpoint_id}/chat"),
    ("POST", "/api/endpoints/{endpoint_id}/forget"),
    ("POST", "/api/endpoints/{endpoint_id}/operation"),
    ("POST", "/api/endpoints/pairing-tokens"),
    ("GET", "/api/endpoints"),
    ("GET", "/api/endpoints/{endpoint_id}"),
    ("PATCH", "/api/endpoints/{endpoint_id}"),
    ("POST", "/api/endpoints/{endpoint_id}/revoke"),
    ("POST", "/api/endpoints/{endpoint_id}/upload"),
    ("POST", "/api/endpoints/{endpoint_id}/download"),
    ("POST", "/api/endpoints/{endpoint_id}/desktop/session"),
    ("GET", "/api/endpoints/{endpoint_id}/desktop/frames"),
    ("POST", "/api/endpoints/{endpoint_id}/desktop/control"),
    ("POST", "/api/endpoints/{endpoint_id}/desktop/input"),
    ("POST", "/api/endpoints/{endpoint_id}/desktop/stop"),
}


class PairInput(Strict):
    token: str = Field(min_length=32, max_length=128)
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")
    temporary: bool = True


class Forget(Strict):
    confirmed: bool


class ManualOperation(Strict):
    operation: str = Field(max_length=64)
    arguments: dict[str, Any]


class Rename(Strict):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")


class Download(Strict):
    path: str = Field(min_length=1, max_length=2048)


class DesktopSession(Strict):
    session_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class Control(DesktopSession):
    enabled: bool


class Input(DesktopSession):
    sequence: int = Field(ge=1)
    operation: str = Field(pattern=r"^desktop\.(click|move|type|key|scroll)$")
    arguments: dict[str, Any]


async def bounded_body(request: Request, maximum: int) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > maximum:
            raise HTTPException(413, "Request exceeds limit.")
        data.extend(chunk)
    return bytes(data)


def install_endpoint_routes(
    app: FastAPI,
    manager: EndpointManager,
    sessions: BrowserSessions | None,
    remote: RemoteAccessConfig,
) -> None:
    views = manager.views

    def available() -> None:
        if not getattr(app.state.application, "endpoint_enabled", False):
            raise HTTPException(404, "Not found.")

    def owner(request: Request, mutation: bool = False) -> None:
        available()
        if remote.enabled and (
            sessions is None or sessions.expiry(request.cookies.get(COOKIE_NAME)) is None
        ):
            raise HTTPException(401, "Authentication required.")
        if mutation:
            origin = remote.public_origin if remote.enabled else str(request.base_url).rstrip("/")
            if request.headers.get("origin") != origin:
                raise HTTPException(403, "Trusted origin required.")

    def endpoint(endpoint_id: str) -> dict[str, Any]:
        row = next((item for item in manager.list() if item["endpoint_id"] == endpoint_id), None)
        if row is None:
            raise HTTPException(404, "Endpoint not found.")
        return row

    async def rpc(endpoint_id: str, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        application = app.state.application
        public_operation = (
            "file.write"
            if operation in {"transfer.begin", "transfer.chunk", "transfer.finish"}
            else operation
        )
        definition = application.registry.definition(f"endpoint.{public_operation}")
        policy = application.mutation_authorization
        if definition is not None and policy is not None:
            principal = application.access.current_principal()
            scope = RuntimeScope(
                session_id="manual-endpoint-control",
                endpoint_id=endpoint_id,
                principal_id=principal.principal_id,
                workspace_id=principal.workspace_id,
            )
            if not policy.authorizes(definition, {"target_ref": endpoint_id, **args}, scope):
                raise HTTPException(403, "Server endpoint execution policy denied.")
        try:
            return await manager.dispatch(endpoint_id, operation, args)
        except EndpointError as error:
            raise HTTPException(409, error.code) from None
        except ValueError:
            raise HTTPException(422, "Invalid endpoint request.") from None

    def view(endpoint_id: str, session_id: str, request: Request) -> dict[str, Any]:
        owner(request)
        row = views.get(session_id)
        if (
            row is None
            or row["endpoint_id"] != endpoint_id
            or row["cookie"] != request.cookies.get(COOKIE_NAME)
            or row["expires"] < time.monotonic()
        ):
            raise HTTPException(409, "Desktop session unavailable.")
        if not endpoint(endpoint_id)["online"] or row["connection"] is not manager.connections.get(
            endpoint_id
        ):
            stop(session_id)
            raise HTTPException(409, "Endpoint disconnected.")
        return row

    def stop(session_id: str) -> None:
        row = views.pop(session_id, None)
        if row:
            target = row["endpoint_id"]
            if manager.controllers.get(target) == session_id:
                manager.controllers.pop(target, None)
            manager.store.audit(target, "manual_session_stopped")

    @app.post("/api/endpoints/pairing-tokens")
    async def pairing_token(request: Request) -> dict[str, Any]:
        owner(request, True)
        try:
            return manager.store.token()
        except ValueError:
            raise HTTPException(429, "Pairing capacity reached.") from None

    @app.post("/api/endpoints/pair")
    async def pair(request: Request) -> Response:
        available()
        # This device bootstrap never accepts browser Origin or browser-cookie authority.
        if request.headers.get("origin") is not None:
            raise HTTPException(403, "Device bootstrap only.")
        try:
            body = PairInput.model_validate_json(await bounded_body(request, 2048))
            identity = manager.store.pair(body.token, body.name, temporary=body.temporary)
        except ValueError:
            raise HTTPException(401, "Pairing rejected.") from None
        return Response(
            json.dumps(identity),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/endpoints/{endpoint_id}/end")
    async def end_device(endpoint_id: str, request: Request) -> dict[str, bool]:
        available()
        credential = request.headers.get("authorization", "")
        if (
            request.headers.get("origin") is not None
            or request.url.query
            or not credential.startswith("Bearer ")
            or len(credential) > 256
            or not manager.store.authenticate(endpoint_id, credential[7:])
        ):
            raise HTTPException(401, "Device authentication required.")
        await manager.revoke(endpoint_id)
        return {"ended": True}

    @app.get("/api/endpoints/artifacts")
    async def worker_artifacts(request: Request) -> dict[str, Any]:
        owner(request)
        from orion.endpoints.artifacts import compatible_artifacts

        return await compatible_artifacts()

    @app.post("/api/endpoints/{endpoint_id}/chat")
    async def device_chat(endpoint_id: str, request: Request) -> dict[str, Any]:
        owner(request, True)
        endpoint(endpoint_id)
        application = app.state.application
        principal = application.access.current_principal()
        session_id = manager.store.device_chat(
            endpoint_id, principal.principal_id, principal.workspace_id
        )
        identity = application.store.session_identity(session_id)
        return {"session_id": session_id, **identity}

    @app.post("/api/endpoints/{endpoint_id}/forget")
    async def forget(endpoint_id: str, request: Request) -> dict[str, bool]:
        owner(request, True)
        endpoint(endpoint_id)
        try:
            body = Forget.model_validate_json(await bounded_body(request, 256))
            if not body.confirmed:
                raise ValueError("confirmation_required")
        except ValueError:
            raise HTTPException(422, "Explicit confirmation required.") from None
        await manager.revoke(endpoint_id)
        try:
            manager.store.forget(endpoint_id)
        except RuntimeError:
            raise HTTPException(
                409, "Finish or cancel Device Chat requests before forgetting."
            ) from None
        return {"forgotten": True}

    @app.post("/api/endpoints/{endpoint_id}/operation")
    async def manual_operation(endpoint_id: str, request: Request) -> dict[str, Any]:
        owner(request, True)
        endpoint(endpoint_id)
        try:
            body = ManualOperation.model_validate_json(await bounded_body(request, 65536))
            # Desktop input requires the separate exclusive control session.
            if body.operation not in OPERATIONS or body.operation.startswith("desktop."):
                raise ValueError("invalid_operation")
            OPERATIONS[body.operation][0].model_validate(body.arguments)
        except ValueError:
            raise HTTPException(422, "Invalid endpoint operation.") from None
        manager.store.audit(endpoint_id, "manual_operation")
        return await rpc(endpoint_id, body.operation, body.arguments)

    @app.websocket("/api/endpoints/{endpoint_id}/worker")
    async def worker(socket: WebSocket, endpoint_id: str) -> None:
        header = socket.headers.get("authorization", "")
        if (
            not getattr(app.state.application, "endpoint_enabled", False)
            or socket.headers.get("origin") is not None
            or socket.url.query
            or not re.fullmatch(r"[0-9a-f]{32}", endpoint_id)
            or not header.startswith("Bearer ")
            or len(header) > 256
            or not manager.store.authenticate(endpoint_id, header[7:])
        ):
            await socket.close(code=1008)
            return
        await manager.attach(endpoint_id, socket)

    @app.get("/api/endpoints")
    async def list_endpoints(request: Request) -> list[dict[str, Any]]:
        owner(request)
        return manager.list()

    @app.get("/api/endpoints/{endpoint_id}")
    async def get_endpoint(endpoint_id: str, request: Request) -> dict[str, Any]:
        owner(request)
        return endpoint(endpoint_id)

    @app.patch("/api/endpoints/{endpoint_id}")
    async def rename(endpoint_id: str, request: Request) -> dict[str, Any]:
        owner(request, True)
        endpoint(endpoint_id)
        try:
            body = Rename.model_validate_json(await bounded_body(request, 2048))
        except ValueError:
            raise HTTPException(422, "Invalid display name.") from None
        manager.store.rename(endpoint_id, body.name)
        return endpoint(endpoint_id)

    @app.post("/api/endpoints/{endpoint_id}/revoke")
    async def revoke(endpoint_id: str, request: Request) -> dict[str, bool]:
        owner(request, True)
        endpoint(endpoint_id)
        await manager.revoke(endpoint_id)
        for key, row in list(views.items()):
            if row["endpoint_id"] == endpoint_id:
                stop(key)
        return {"revoked": True}

    @app.post("/api/endpoints/{endpoint_id}/upload")
    async def upload(endpoint_id: str, request: Request) -> dict[str, Any]:
        owner(request, True)
        path = request.headers.get("x-endpoint-path", "")
        overwrite = request.headers.get("x-overwrite", "false")
        if overwrite not in {"true", "false"}:
            raise HTTPException(422, "Invalid overwrite flag.")
        transfer_id, offset = uuid.uuid4().hex, 0
        try:
            await rpc(
                endpoint_id,
                "transfer.begin",
                {"transfer_id": transfer_id, "path": path, "overwrite": overwrite == "true"},
            )
            async for chunk in request.stream():
                if offset + len(chunk) > MAX_TRANSFER:
                    raise HTTPException(413, "Transfer exceeds limit.")
                for start in range(0, len(chunk), CHUNK_SIZE):
                    part = chunk[start : start + CHUNK_SIZE]
                    await rpc(
                        endpoint_id,
                        "transfer.chunk",
                        {
                            "transfer_id": transfer_id,
                            "content_b64": base64.b64encode(part).decode(),
                            "offset": offset,
                        },
                    )
                    offset += len(part)
            return await rpc(endpoint_id, "transfer.finish", {"transfer_id": transfer_id})
        finally:
            with contextlib.suppress(Exception):
                await asyncio.shield(
                    manager.dispatch(endpoint_id, "transfer.abort", {"transfer_id": transfer_id})
                )

    @app.post("/api/endpoints/{endpoint_id}/download")
    async def download(endpoint_id: str, request: Request) -> StreamingResponse:
        owner(request, True)
        try:
            body = Download.model_validate_json(await bounded_body(request, 4096))
        except ValueError:
            raise HTTPException(422, "Invalid path.") from None
        first = await rpc(
            endpoint_id, "file.read", {"path": body.path, "offset": 0, "length": CHUNK_SIZE}
        )
        size = first.get("size")
        if not isinstance(size, int) or size < 0 or size > MAX_TRANSFER:
            raise HTTPException(413, "Transfer exceeds limit.")

        async def chunks() -> Any:
            offset, result = 0, first
            while offset < size:
                raw = base64.b64decode(result.get("content_b64", ""), validate=True)
                if (
                    not raw
                    or len(raw) > CHUNK_SIZE
                    or offset + len(raw) > size
                    or result.get("size") != size
                    or result.get("file_identity") != first.get("file_identity")
                ):
                    raise EndpointError("interrupted")
                yield raw
                offset += len(raw)
                if offset < size:
                    result = await manager.dispatch(
                        endpoint_id,
                        "file.read",
                        {
                            "path": body.path,
                            "offset": offset,
                            "length": min(CHUNK_SIZE, size - offset),
                        },
                    )

        return StreamingResponse(
            chunks(),
            media_type="application/octet-stream",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'attachment; filename="endpoint-download"',
            },
        )

    @app.post("/api/endpoints/{endpoint_id}/desktop/session")
    async def desktop_session(endpoint_id: str, request: Request) -> dict[str, Any]:
        owner(request, True)
        try:
            capture = Capture.model_validate_json((await bounded_body(request, 2048)) or b"{}")
        except ValueError:
            raise HTTPException(422, "Invalid monitor selection.") from None
        for key, row in list(views.items()):
            if row["expires"] < time.monotonic():
                stop(key)
        target = endpoint(endpoint_id)
        if (
            not target["online"]
            or "screen.capture" not in target["capabilities"]
            or len(views) >= 32
        ):
            raise HTTPException(409, "Desktop capture unavailable.")
        key = uuid.uuid4().hex
        views[key] = {
            "endpoint_id": endpoint_id,
            "cookie": request.cookies.get(COOKIE_NAME),
            "expires": time.monotonic() + 1800,
            "sequence": 0,
            "streaming": False,
            "monitor": capture.monitor,
            "connection": manager.connections.get(endpoint_id),
        }
        manager.store.audit(endpoint_id, "manual_session_started")
        return {"session_id": key, "control_available": "desktop.click" in target["capabilities"]}

    @app.get("/api/endpoints/{endpoint_id}/desktop/frames")
    async def frames(endpoint_id: str, request: Request) -> StreamingResponse:
        session_id = request.headers.get("x-desktop-session", "")
        row = view(endpoint_id, session_id, request)
        if row["streaming"]:
            raise HTTPException(409, "View already streaming.")
        row["streaming"] = True

        async def stream() -> Any:
            try:
                while True:
                    view(endpoint_id, session_id, request)
                    frame = await manager.dispatch(
                        endpoint_id, "screen.capture", {"monitor": row["monitor"]}
                    )
                    yield json.dumps(frame) + "\n"
                    await asyncio.sleep(max(0.2, 1 / min(5, max(1, frame.get("max_fps", 1)))))
            finally:
                stop(session_id)

        return StreamingResponse(
            stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"}
        )

    @app.post("/api/endpoints/{endpoint_id}/desktop/control")
    async def control(endpoint_id: str, request: Request) -> dict[str, bool]:
        owner(request, True)
        try:
            body = Control.model_validate_json(await bounded_body(request, 12000))
        except ValueError:
            raise HTTPException(422, "Invalid desktop request.") from None
        view(endpoint_id, body.session_id, request)
        if body.enabled:
            if "desktop.click" not in endpoint(endpoint_id)[
                "capabilities"
            ] or manager.controllers.get(endpoint_id) not in {None, body.session_id}:
                raise HTTPException(409, "Control unavailable or already owned.")
            manager.controllers[endpoint_id] = body.session_id
        elif manager.controllers.get(endpoint_id) == body.session_id:
            manager.controllers.pop(endpoint_id, None)
        manager.store.audit(
            endpoint_id, "manual_control_enabled" if body.enabled else "manual_control_disabled"
        )
        return {"enabled": body.enabled}

    @app.post("/api/endpoints/{endpoint_id}/desktop/input")
    async def desktop_input(endpoint_id: str, request: Request) -> dict[str, Any]:
        owner(request, True)
        try:
            body = Input.model_validate_json(await bounded_body(request, 12000))
        except ValueError:
            raise HTTPException(422, "Invalid desktop request.") from None
        row = view(endpoint_id, body.session_id, request)
        if (
            manager.controllers.get(endpoint_id) != body.session_id
            or body.sequence != row["sequence"] + 1
        ):
            raise HTTPException(409, "Control session or input sequence rejected.")
        row["sequence"] = body.sequence
        try:
            OPERATIONS[body.operation][0].model_validate(body.arguments)
        except ValueError:
            raise HTTPException(422, "Invalid desktop input.") from None
        return await rpc(endpoint_id, body.operation, body.arguments)

    @app.post("/api/endpoints/{endpoint_id}/desktop/stop")
    async def desktop_stop(endpoint_id: str, request: Request) -> dict[str, bool]:
        owner(request, True)
        try:
            body = DesktopSession.model_validate_json(await bounded_body(request, 12000))
        except ValueError:
            raise HTTPException(422, "Invalid desktop request.") from None
        row = views.get(body.session_id)
        if row and (
            row["endpoint_id"] != endpoint_id or row["cookie"] != request.cookies.get(COOKIE_NAME)
        ):
            raise HTTPException(403, "Desktop session unavailable.")
        stop(body.session_id)
        return {"stopped": True}
