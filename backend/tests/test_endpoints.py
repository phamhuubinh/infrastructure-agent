"""Endpoint trust boundaries, transport failures and native worker contracts."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import ScriptedBackend
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from orion.api.app import create_app
from orion.api.endpoints import DEVICE_WS_ROUTES, ENDPOINT_OWNER_ROUTES, PAIRING_API_ROUTES
from orion.bootstrap import build_application
from orion.contracts import ModelToolCall, RuntimeScope
from orion.endpoints.manager import Connection, EndpointError, EndpointManager
from orion.endpoints.persistence import EndpointStore
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.mutation_authorization import MutationAuthorizationPolicy
from orion.tool_runtime.runner import ToolRunner
from orion_endpoint.desktop import Desktop
from orion_endpoint.executor import Executor
from orion_endpoint.policy import Policy
from orion_endpoint.protocol import (
    MAX_MESSAGE,
    OPERATIONS,
    Hello,
    Request,
    Result,
    decode,
    validate_url,
)


@pytest.fixture(autouse=True)
def endpoint_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORION_ENDPOINTS", "1")


@pytest.fixture
def identities(tmp_path: Path) -> Any:
    store = SQLiteStore(tmp_path / "orion.db")
    endpoints = EndpointStore(store)
    yield endpoints
    store.close()


def paired(store: EndpointStore) -> dict[str, str]:
    return store.pair(store.token()["token"], "Endpoint test")


def test_pairing_atomic_digest_expiry_rate_limit_and_restart(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "orion.db")
    now = [10.0]
    endpoints = EndpointStore(store, lambda: now[0])
    token = endpoints.token()["token"]
    identity = endpoints.pair(token, "Safe label")
    assert endpoints.authenticate(identity["endpoint_id"], identity["credential"])
    assert not endpoints.authenticate(uuid.uuid4().hex, identity["credential"])
    assert not endpoints.authenticate(identity["endpoint_id"], "wrong")
    with pytest.raises(ValueError):
        endpoints.pair(token, "replay")
    contents = " ".join(
        str(tuple(row))
        for table in ("endpoint_identities", "endpoint_pairing_tokens", "endpoint_audit")
        for row in store._connection.execute(f"SELECT * FROM {table}")
    )
    assert token not in contents and identity["credential"] not in contents
    expiring = endpoints.token()["token"]
    now[0] += 301
    with pytest.raises(ValueError):
        endpoints.pair(expiring, "expired")
    for _ in range(10):
        with pytest.raises(ValueError):
            endpoints.pair("invalid", "invalid")
    with pytest.raises(ValueError):
        endpoints.pair(endpoints.token()["token"], "rate limited")
    manager = EndpointManager(endpoints)
    endpoints.update_connection(
        identity["endpoint_id"],
        Hello(platform="linux", worker_version="test", capabilities=[]),
        "connected",
    )
    assert not manager.list()[0]["online"]
    endpoints.revoke(identity["endpoint_id"])
    assert not endpoints.authenticate(identity["endpoint_id"], identity["credential"])
    store.close()
    reopened = SQLiteStore(tmp_path / "orion.db")
    assert EndpointStore(reopened).get(identity["endpoint_id"])["revoked_at"] is not None
    reopened.close()


def test_pairing_capacity_and_parallel_one_use(identities: EndpointStore) -> None:
    token = identities.token()["token"]
    results = []

    def consume() -> None:
        try:
            results.append(identities.pair(token, "race"))
        except ValueError:
            results.append(None)

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(result is not None for result in results) == 1
    for _ in range(15):
        identities.token()
    with pytest.raises(ValueError, match="capacity"):
        identities.token()


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.test",
        "https://a.test/path",
        "https://user:secret@a.test",
        "https://a.test?token=x",
        "ws://localhost",
    ],
)
def test_tls_and_no_url_credentials(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url)
    assert validate_url("http://127.0.0.1:1234") == "http://127.0.0.1:1234"
    assert validate_url("https://orion.test") == "https://orion.test"


@pytest.mark.parametrize(
    "raw",
    [
        '{"type":"hello","version":2,"platform":"linux","worker_version":"x","capabilities":[]}',
        '{"type":"ping","principal_id":"admin"}',
        '{"type":"unknown"}',
        "x" * (MAX_MESSAGE + 1),
        '{"type":"result","request_id":"'
        + "a" * 32
        + '","data":'
        + "[" * 15
        + "0"
        + "]" * 15
        + "}",
    ],
)
def test_message_bounds_and_closed_protocol(raw: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        decode(raw)


class FakeSocket:
    def __init__(self, reply: bool = True) -> None:
        self.connection: Connection | None = None
        self.messages: list[Any] = []
        self.reply = reply
        self.data = {"observed": True}
        self.closed = False

    async def send_text(self, text: str) -> None:
        message = decode(text)
        self.messages.append(message)
        if self.reply and isinstance(message, Request):
            assert self.connection is not None
            self.connection.pending[message.request_id][0].set_result(
                Result(request_id=message.request_id, data=self.data)
            )

    async def close(self, code: int = 1000) -> None:
        self.closed = True


def connection(manager: EndpointManager, target: str, *, reply: bool = True) -> FakeSocket:
    socket = FakeSocket(reply)
    session = Connection(
        socket, Hello(platform="linux", worker_version="test", capabilities=list(OPERATIONS))
    )  # type: ignore[arg-type]
    socket.connection = session
    manager.connections[target] = session
    return socket


def test_dispatch_scope_cancellation_disconnect_uncertainty_and_shutdown(
    identities: EndpointStore,
) -> None:
    async def scenario() -> None:
        target = paired(identities)["endpoint_id"]
        manager = EndpointManager(identities, timeout=0.03)
        socket = connection(manager, target)
        result = await manager.dispatch(target, "system.inspect", {})
        assert result == {"observed": True}
        wire = socket.messages[-1].model_dump()
        assert set(wire) == {"type", "request_id", "operation", "arguments"}
        with pytest.raises(EndpointError, match="cancelled"):
            await manager.dispatch(target, "file.mkdir", {"path": "/test"}, lambda: True)
        assert len(socket.messages) == 1
        socket.reply = False
        with pytest.raises(EndpointError, match="outcome_unknown"):
            await manager.dispatch(target, "file.mkdir", {"path": "/test"})
        assert len([message for message in socket.messages if isinstance(message, Request)]) == 2
        assert not socket.connection.pending
        task = asyncio.create_task(manager.dispatch(target, "file.mkdir", {"path": "/test"}))
        await asyncio.sleep(0.005)
        await manager.detach(target, socket.connection)
        with pytest.raises(EndpointError, match="outcome_unknown"):
            await task
        connection(manager, target)
        assert len(socket.messages) == 4  # No replay on new connection.
        await manager.close()
        assert not manager.connections and not manager.controllers
        with pytest.raises(EndpointError, match="unavailable"):
            await manager.dispatch(target, "system.inspect", {})

    asyncio.run(scenario())


def test_bounded_inflight_and_no_mutation_overlap(identities: EndpointStore) -> None:
    async def scenario() -> None:
        target = paired(identities)["endpoint_id"]
        manager = EndpointManager(identities, timeout=0.05)
        socket = connection(manager, target, reply=False)
        tasks = [
            asyncio.create_task(manager.dispatch(target, "file.mkdir", {"path": "/test"}))
            for _ in range(4)
        ]
        await asyncio.sleep(0.005)
        assert len(socket.messages) == 1
        with pytest.raises(EndpointError, match="busy"):
            await manager.dispatch(target, "system.inspect", {})
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert not socket.connection.pending
        await manager.close()

    asyncio.run(scenario())


def test_registry_stable_runner_scheduler_and_target_policy(tmp_path: Path) -> None:
    application = build_application(tmp_path / "orion.db", ScriptedBackend([]))
    before = tuple(application.registry.definitions())
    assert {
        definition.name for definition in before if definition.name.startswith("endpoint.")
    } == {"endpoint.list", *(f"endpoint.{name}" for name in OPERATIONS)}
    target = paired(application.endpoints.store)["endpoint_id"]
    scope = RuntimeScope(session_id="chat", principal_id="local", workspace_id="local")
    call = ModelToolCall(
        call_id="call",
        tool_name="endpoint.file.mkdir",
        arguments={"target_ref": target, "path": "/test"},
    )

    async def scenario() -> None:
        socket = connection(application.endpoints, target)
        policy = MutationAuthorizationPolicy(
            None, lambda family, ref: application.endpoints.configured(ref)
        )
        runner = ToolRunner(application.registry, mutation_authorization=policy)
        assert (await runner.run_async(call, scope)).status == "success"
        for runner in (
            ToolRunner(application.registry, {"mutation"}, policy),
            ToolRunner(application.registry, mutation_authorization=MutationAuthorizationPolicy()),
        ):
            assert (await runner.run_async(call, scope)).error.code == "operation_blocked"
        await application.endpoints.close()
        assert tuple(application.registry.definitions()) == before
        assert socket.messages

    asyncio.run(scenario())
    application.store.close()


def test_api_auth_route_categories_and_real_websocket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.routing import APIWebSocketRoute

    from orion.access.remote import RemoteAccessConfig, hash_password

    origin = "https://127.0.0.1:61888"
    remote = RemoteAccessConfig(True, "127.0.0.1", origin, hash_password("password"))
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]), remote_config=remote)
    actual = {
        ("WEBSOCKET", route.path) for route in app.routes if isinstance(route, APIWebSocketRoute)
    }
    assert actual == DEVICE_WS_ROUTES
    assert ENDPOINT_OWNER_ROUTES.isdisjoint(PAIRING_API_ROUTES)
    with TestClient(app, base_url=origin) as client:
        assert client.get("/api/endpoints").status_code == 401
        assert (
            client.post("/api/endpoints/pairing-tokens", headers={"Origin": origin}).status_code
            == 401
        )
        assert (
            client.post("/api/endpoints/pair", json={"token": "x" * 32, "name": "test"}).status_code
            == 401
        )
        assert client.get("/api/no-such-route").status_code == 404
        assert (
            client.post(
                "/api/auth/login", json={"password": "password"}, headers={"Origin": origin}
            ).status_code
            == 200
        )
        assert client.post("/api/endpoints/pairing-tokens").status_code == 403
        token = client.post("/api/endpoints/pairing-tokens", headers={"Origin": origin}).json()[
            "token"
        ]
        assert (
            client.post(
                "/api/endpoints/pair",
                json={"token": token, "name": "test"},
                headers={"Origin": origin},
            ).status_code
            == 403
        )
        identity = client.post("/api/endpoints/pair", json={"token": token, "name": "test"}).json()
        target, credential = identity["endpoint_id"], identity["credential"]
        for headers in (
            {},
            {"Authorization": "Bearer wrong"},
            {"Authorization": f"Bearer {credential}", "Origin": "https://evil.test"},
        ):
            with (
                pytest.raises(WebSocketDisconnect),
                client.websocket_connect(f"/api/endpoints/{target}/worker", headers=headers),
            ):
                pass
        with client.websocket_connect(
            f"/api/endpoints/{target}/worker", headers={"Authorization": f"Bearer {credential}"}
        ) as socket:
            socket.send_text(
                Hello(
                    platform="linux", worker_version="test", capabilities=["system.inspect"]
                ).model_dump_json()
            )
            assert socket.receive_json()["type"] == "welcome"
            assert client.get("/api/endpoints").json()[0]["online"]
            with (
                pytest.raises(WebSocketDisconnect),
                client.websocket_connect(
                    f"/api/endpoints/{target}/worker",
                    headers={"Authorization": f"Bearer {credential}"},
                ),
            ):
                pass
            assert (
                client.patch(
                    f"/api/endpoints/{target}", json={"name": "Renamed"}, headers={"Origin": origin}
                ).status_code
                == 200
            )
        assert not client.get("/api/endpoints").json()[0]["online"]
        assert (
            client.post(f"/api/endpoints/{target}/revoke", headers={"Origin": origin}).status_code
            == 200
        )
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                f"/api/endpoints/{target}/worker", headers={"Authorization": f"Bearer {credential}"}
            ),
        ):
            pass
        visible = client.get("/api/endpoints").text
        assert credential not in visible and "digest" not in visible and token not in visible


def test_worker_policy_files_atomic_transfer_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "path with spaces"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    policy = Policy(read_roots=[str(root)], write_roots=[str(root)])
    executor = Executor(policy)
    path = str(root / "test.txt")

    async def scenario() -> None:
        assert (await executor.hello()).capabilities == sorted(
            {
                "system.inspect",
                "process.list",
                "file.list",
                "file.read",
                "file.write",
                "file.mkdir",
                "file.delete",
                "file.move",
            }
        )
        await executor.execute("file.write", {"path": path, "content": "original"})
        with pytest.raises(FileExistsError):
            await executor.execute("file.write", {"path": path, "content": "overwrite denied"})
        assert (await executor.execute("file.read", {"path": path, "offset": 1, "length": 3}))[
            "text"
        ] == "rig"
        for bad in (str(outside / "escape"), str(root / ".." / "outside" / "escape"), "relative"):
            with pytest.raises(PermissionError):
                await executor.execute("file.write", {"path": bad, "content": "x"})
        key = uuid.uuid4().hex
        destination = str(root / "upload.bin")
        await executor.execute("transfer.begin", {"transfer_id": key, "path": destination})
        await executor.execute(
            "transfer.chunk",
            {"transfer_id": key, "offset": 0, "content_b64": base64.b64encode(b"payload").decode()},
        )
        with pytest.raises(ValueError):
            await executor.execute(
                "transfer.chunk", {"transfer_id": key, "offset": 0, "content_b64": "eA=="}
            )
        await executor.execute("transfer.finish", {"transfer_id": key})
        assert Path(destination).read_bytes() == b"payload"
        await executor.execute(
            "file.move", {"path": destination, "destination": str(root / "moved")}
        )
        await executor.execute("file.delete", {"path": str(root / "moved")})
        await executor.execute("file.mkdir", {"path": str(root / "sub")})
        assert (await executor.execute("file.list", {"path": str(root / "sub")}))["entries"] == []
        pending = uuid.uuid4().hex
        await executor.execute(
            "transfer.begin", {"transfer_id": pending, "path": str(root / "cancelled")}
        )
        await executor.close()
        assert not list(root.glob(".orion-upload-*"))
        assert not (root / "cancelled").exists()

    asyncio.run(scenario())
    if os.name != "nt":
        (root / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(PermissionError):
            policy.path(str(root / "link" / "escape"), write=True)
    with pytest.raises(ValidationError):
        Policy.model_validate({"shell": True})
    with pytest.raises(PermissionError):
        Policy().path(path)


def test_worker_process_desktop_and_browser_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    executor = Executor(Policy())

    async def scenario() -> None:
        assert (await executor.execute("system.inspect", {}))["cpu_count"]
        rows = (await executor.execute("process.list", {"limit": 1}))["processes"]
        assert len(rows) <= 1 and all(set(row) == {"pid", "name", "created_at"} for row in rows)
        for operation, arguments in (
            ("process.start", {"alias": "shell"}),
            ("process.terminate", {"pid": 1, "expected_name": "test", "expected_created_at": 1.0}),
            ("screen.capture", {}),
            ("desktop.click", {"x": 0, "y": 0}),
            ("browser.open", {"url": "http://localhost"}),
        ):
            with pytest.raises(PermissionError):
                await executor.execute(operation, arguments)
        assert not Desktop(Policy(desktop_capture=True)).available() if os.name != "nt" else True
        await executor.close()

    asyncio.run(scenario())
    for operation, arguments in (
        ("desktop.key", {"key": "eval"}),
        ("desktop.click", {"x": -1, "y": 0}),
        ("desktop.type", {"text": "x" * 4097}),
        ("file.read", {"path": "/test", "length": 100000}),
    ):
        with pytest.raises(ValidationError):
            OPERATIONS[operation][0].model_validate(arguments)
    assert not any("eval" in name or "shell" in name for name in OPERATIONS)


@pytest.mark.parametrize(
    "mode,approve", [("read_only", False), ("auto", True), ("confirm", True), ("confirm", False)]
)
@pytest.mark.parametrize("project", [False, True])
def test_endpoint_chat_project_confirmation_and_payload_privacy(
    tmp_path: Path, mode: str, approve: bool, project: bool
) -> None:
    from orion.contracts import AssistantMessage, ModelTurn
    from orion.tool_runtime.mutation_authorization import MutationMode

    async def scenario() -> None:
        backend = ScriptedBackend([])
        application = build_application(tmp_path / "chat.db", backend)
        target = paired(application.endpoints.store)["endpoint_id"]
        socket = connection(application.endpoints, target)
        call = ModelToolCall(
            call_id="mutation",
            tool_name="endpoint.file.write",
            arguments={
                "target_ref": target,
                "path": "/safe/path",
                "content": "secret-file-payload",
            },
        )
        backend.turns = [
            ModelTurn(tool_calls=(call,)),
            *[
                ModelTurn(
                    assistant=AssistantMessage(
                        content="The endpoint operation was blocked."
                        if not approve
                        else "Observed the endpoint response."
                    )
                )
                for _ in range(4)
            ],
        ]
        store = application.store
        store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
        project_id = store.create_project("Endpoint project")["project_id"] if project else None
        session = store.create_session(project_id=project_id)
        store.set_session_mutation_mode(session, MutationMode(mode))
        request_id = application.runtime.begin(session, "Write the explicit file")
        task = asyncio.create_task(application.runtime.run(session, request_id))
        if mode == "confirm":
            for _ in range(100):
                pending = store.pending_authorization(request_id, "mutation")
                if pending:
                    break
                await asyncio.sleep(0.005)
            assert pending is not None
            assert "secret-file-payload" not in json.dumps(pending)
            assert not socket.messages
            assert application.runtime.resolve_authorization(
                session, request_id, "mutation", approve
            )
            assert not application.runtime.resolve_authorization(
                session, request_id, "mutation", approve
            )
        await task
        assert bool(socket.messages) == (mode == "auto" or (mode == "confirm" and approve))
        timeline = json.dumps([item.model_dump(mode="json") for item in store.timeline(session)])
        assert "secret-file-payload" not in timeline
        if socket.messages:
            assert "observed" in " ".join(message.content for message in backend.calls[1][0])
        assert not application.runtime._transient_endpoint_results
        await application.endpoints.close()
        store.close()

    asyncio.run(scenario())


def test_cancellation_after_dispatch_is_unknown(identities: EndpointStore) -> None:
    async def scenario() -> None:
        target = paired(identities)["endpoint_id"]
        manager = EndpointManager(identities)
        socket = connection(manager, target, reply=False)
        cancelled = [False]
        task = asyncio.create_task(
            manager.dispatch(target, "file.mkdir", {"path": "/safe"}, lambda: cancelled[0])
        )
        await asyncio.sleep(0.005)
        cancelled[0] = True
        with pytest.raises(EndpointError, match="outcome_unknown"):
            await task
        assert len([message for message in socket.messages if isinstance(message, Request)]) == 1
        await manager.close()

    asyncio.run(scenario())


def test_handshake_bad_version_capability_and_identity_binding(tmp_path: Path) -> None:
    app = create_app(tmp_path / "protocol.db", ScriptedBackend([]))
    store = app.state.application.endpoints.store
    first, second = paired(store), paired(store)
    with TestClient(app) as client:
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                f"/api/endpoints/{second['endpoint_id']}/worker",
                headers={"Authorization": f"Bearer {first['credential']}"},
            ),
        ):
            pass
        for hello in (
            {
                "type": "hello",
                "version": 2,
                "platform": "linux",
                "worker_version": "test",
                "capabilities": [],
            },
            {
                "type": "hello",
                "version": 1,
                "platform": "linux",
                "worker_version": "test",
                "capabilities": ["shell.execute"],
            },
        ):
            with client.websocket_connect(
                f"/api/endpoints/{first['endpoint_id']}/worker",
                headers={"Authorization": f"Bearer {first['credential']}"},
            ) as socket:
                socket.send_json(hello)
                with pytest.raises(WebSocketDisconnect):
                    socket.receive_json()
        for _ in range(2):
            with client.websocket_connect(
                f"/api/endpoints/{first['endpoint_id']}/worker",
                headers={"Authorization": f"Bearer {first['credential']}"},
            ) as socket:
                socket.send_text(
                    Hello(
                        platform="linux", worker_version="test", capabilities=[]
                    ).model_dump_json()
                )
                assert socket.receive_json()["type"] == "welcome"


def test_transfer_abort_bounds_root_access_and_shell_alias(tmp_path: Path) -> None:
    import sys

    from orion_endpoint.policy import ApplicationAlias

    root = tmp_path / "root"
    root.mkdir()
    executor = Executor(
        Policy(
            read_roots=[str(root)],
            write_roots=[str(root)],
            applications={"python": ApplicationAlias(executable=sys.executable)},
        )
    )

    async def scenario() -> None:
        assert (await executor.execute("file.list", {"path": str(root)}))["entries"] == []
        key = uuid.uuid4().hex
        await executor.execute("transfer.begin", {"transfer_id": key, "path": str(root / "cancel")})
        await executor.execute("transfer.abort", {"transfer_id": key})
        assert not list(root.iterdir())
        with pytest.raises(PermissionError):
            await executor.execute("process.start", {"alias": "python"})
        await executor.close()

    asyncio.run(scenario())


def test_every_endpoint_mutation_is_blocked_for_scheduler(tmp_path: Path) -> None:
    application = build_application(tmp_path / "scheduler.db", ScriptedBackend([]))
    target = paired(application.endpoints.store)["endpoint_id"]
    runner = ToolRunner(application.registry, {"mutation"})
    scope = RuntimeScope(session_id="scheduled", principal_id="local", workspace_id="local")
    values = {
        "path": "/safe",
        "destination": "/safe2",
        "content": "x",
        "alias": "app",
        "pid": 1,
        "expected_name": "test",
        "expected_created_at": 1.0,
        "text": "x",
        "x": 1,
        "y": 1,
        "key": "enter",
        "dy": 1,
        "url": "http://localhost",
        "selector": "#test",
    }
    for definition in application.registry.definitions():
        if definition.name.startswith("endpoint.") and definition.operation_kind == "mutation":
            arguments = {
                name: target if name == "target_ref" else values[name]
                for name in definition.input_schema["required"]
            }
            result = runner.run(
                ModelToolCall(call_id="scheduled", tool_name=definition.name, arguments=arguments),
                scope,
            )
            assert result.error.code == "operation_blocked", (definition.name, result)
    application.store.close()


def test_worker_heartbeat_liveness_and_safe_failure(tmp_path: Path) -> None:
    app = create_app(tmp_path / "heartbeat.db", ScriptedBackend([]))
    manager = app.state.application.endpoints
    manager.heartbeat = 0.01
    identity = paired(manager.store)
    with TestClient(app) as client:
        with client.websocket_connect(
            f"/api/endpoints/{identity['endpoint_id']}/worker",
            headers={"Authorization": f"Bearer {identity['credential']}"},
        ) as socket:
            socket.send_text(
                Hello(platform="linux", worker_version="test", capabilities=[]).model_dump_json()
            )
            assert socket.receive_json()["type"] == "welcome"
            with pytest.raises(WebSocketDisconnect):
                for _ in range(10):
                    assert socket.receive_json()["type"] == "ping"
        assert not manager.connections


def test_endpoint_read_uses_same_chat_and_transient_evidence(tmp_path: Path) -> None:
    from orion.contracts import AssistantMessage, ModelTurn

    async def scenario() -> None:
        backend = ScriptedBackend([])
        application = build_application(tmp_path / "read.db", backend)
        target = paired(application.endpoints.store)["endpoint_id"]
        socket = connection(application.endpoints, target)
        socket.data["private"] = "endpoint-private-fixture"
        backend.turns = [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="inspect",
                        tool_name="endpoint.system.inspect",
                        arguments={"target_ref": target},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Observed the endpoint.")),
        ]
        application.store.upsert_model_config(
            "openai_compatible", "http://model.test/v1", "fake", None
        )
        session = application.store.create_session()
        from orion.chat.diagnostics import BoundedModelInputDiagnostics

        application.runtime._diagnostic_sink = BoundedModelInputDiagnostics()
        outcome = await application.runtime.submit(session, "Inspect my endpoint")
        assert "endpoint-private-fixture" not in json.dumps(
            application.runtime.diagnostics(outcome.request_id)
        )
        assert socket.messages[0].operation == "system.inspect"
        assert "observed" in " ".join(message.content for message in backend.calls[1][0])
        assert "endpoint.system.inspect" in {definition.name for definition in backend.calls[0][1]}
        assert "observed" not in json.dumps(
            [item.model_dump(mode="json") for item in application.store.timeline(session)]
        )
        await application.endpoints.close()
        application.store.close()

    asyncio.run(scenario())


def test_manual_desktop_exclusive_controller_sequence_and_disconnect(tmp_path: Path) -> None:
    app = create_app(tmp_path / "desktop.db", ScriptedBackend([]))
    manager = app.state.application.endpoints
    target = paired(manager.store)["endpoint_id"]
    socket = connection(manager, target)
    manager.store.update_connection(target, socket.connection.hello, "connected")
    prefix = f"/api/endpoints/{target}/desktop"
    origin = "http://testserver"
    with TestClient(app) as client:
        first = client.post(prefix + "/session", headers={"Origin": origin}).json()["session_id"]
        second = client.post(prefix + "/session", headers={"Origin": origin}).json()["session_id"]
        assert (
            client.post(
                prefix + "/control",
                json={"session_id": first, "enabled": True},
                headers={"Origin": "http://evil"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                prefix + "/control",
                json={"session_id": first, "enabled": True},
                headers={"Origin": origin},
            ).status_code
            == 200
        )
        assert (
            client.post(
                prefix + "/control",
                json={"session_id": second, "enabled": True},
                headers={"Origin": origin},
            ).status_code
            == 409
        )
        input_body = {
            "session_id": first,
            "sequence": 1,
            "operation": "desktop.click",
            "arguments": {"x": 1, "y": 1},
        }
        assert (
            client.post(prefix + "/input", json=input_body, headers={"Origin": origin}).status_code
            == 200
        )
        assert (
            client.post(prefix + "/input", json=input_body, headers={"Origin": origin}).status_code
            == 409
        )
        input_body["sequence"] = 2
        input_body["arguments"] = {"x": -1, "y": 1}
        assert (
            client.post(prefix + "/input", json=input_body, headers={"Origin": origin}).status_code
            == 422
        )
        # A new worker connection cannot revive a stale view/control session.
        connection(manager, target)
        assert (
            client.post(
                prefix + "/control",
                json={"session_id": first, "enabled": True},
                headers={"Origin": origin},
            ).status_code
            == 409
        )
        assert not manager.controllers
    records = manager.store.store._connection.execute("SELECT event FROM endpoint_audit").fetchall()
    assert "manual_control_enabled" in [row[0] for row in records]
    assert "desktop.click" not in [row[0] for row in records]


def test_native_configured_process_alias_and_identity_preflight(tmp_path: Path) -> None:
    import shutil

    from orion_endpoint.policy import ApplicationAlias

    executable = shutil.which("ping.exe" if os.name == "nt" else "sleep")
    assert executable is not None
    args = ["-n", "30", "127.0.0.1"] if os.name == "nt" else ["30"]
    executor = Executor(
        Policy(
            applications={"safe": ApplicationAlias(executable=executable, fixed_args=args)},
            terminate=True,
        )
    )

    async def scenario() -> None:
        with pytest.raises(PermissionError):
            await executor.execute("process.start", {"alias": "safe", "args": ["; eval"]})
        started = await executor.execute("process.start", {"alias": "safe"})
        expected = {
            "pid": started["pid"],
            "expected_name": started["name"],
            "expected_created_at": started["created_at"],
        }
        with pytest.raises(FileExistsError):
            await executor.execute("process.terminate", {**expected, "expected_name": "wrong"})
        assert (await executor.execute("process.terminate", expected))["terminated"]
        await executor.close()
        assert not executor.children

    asyncio.run(scenario())


def test_worker_payload_cannot_enter_authorization_activity_audit(tmp_path: Path) -> None:
    from orion.contracts import ToolResult

    application = build_application(tmp_path / "audit.db", ScriptedBackend([]))
    session = application.store.create_session()
    request = application.store.create_request(session)
    result = ToolResult(
        call_id="call",
        tool_name="endpoint.file.write",
        status="success",
        data={
            "target_ref": "typed-secret",
            "changed": "typed-secret",
            "verification": {"status": "typed-secret"},
        },
    )
    application.runtime._persist_tool_result(session, request, result, 1)
    assert "typed-secret" not in json.dumps(application.store.events(request))
    assert "typed-secret" not in json.dumps(
        [item.model_dump(mode="json") for item in application.store.timeline(session)]
    )
    application.store.close()


def test_local_capture_rate_ceiling_cannot_be_widened(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    waits = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    executor = Executor(
        Policy(desktop_capture=True, max_fps=2), clock=lambda: now[0], sleeper=sleep
    )
    monkeypatch.setattr(executor.desktop, "capture", lambda monitor: {"frame": monitor})

    async def scenario() -> None:
        await executor.execute("screen.capture", {})
        await executor.execute("screen.capture", {})
        assert waits == [0.5]
        await executor.close()

    asyncio.run(scenario())
