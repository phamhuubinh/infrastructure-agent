"""Portable temporary trust lifecycle and endpoint-owned canonical conversations."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import ScriptedBackend
from fastapi.testclient import TestClient

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn
from orion.endpoints.persistence import EndpointStore
from orion.persistence.sqlite import SQLiteStore
from orion.scheduler.contracts import TaskInput
from orion.tool_runtime.mutation_authorization import MutationAuthorizationPolicy, MutationMode
from orion.tool_runtime.runner import ToolRunner


def test_temporary_expiry_reconnect_restart_and_persistent_identity(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "db")
    now = [100.0]
    endpoints = EndpointStore(store, lambda: now[0])
    temporary = endpoints.pair(endpoints.token()["token"], "Temporary", temporary=True)
    persistent = endpoints.pair(endpoints.token()["token"], "Remembered", temporary=False)
    assert endpoints.get(temporary["endpoint_id"])["temporary"]
    assert endpoints.authenticate(**temporary)
    now[0] += 100
    endpoints.update_connection(temporary["endpoint_id"], None, "connected")
    now[0] += 100
    assert endpoints.authenticate(**temporary)
    now[0] += 121
    assert not endpoints.authenticate(**temporary)
    assert endpoints.authenticate(**persistent)
    another = endpoints.pair(endpoints.token()["token"], "Restart", temporary=True)
    store.close()
    reopened = SQLiteStore(tmp_path / "db")
    after = EndpointStore(reopened, lambda: now[0])
    assert not after.authenticate(**another)
    assert after.authenticate(**persistent)
    reopened.close()


def test_device_chat_isolated_persisted_mode_binding_and_forget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORION_ENDPOINTS", "1")
    app = create_app(tmp_path / "db", ScriptedBackend([]))
    origin = {"Origin": "http://testserver"}
    with TestClient(app) as client:
        token = client.post("/api/endpoints/pairing-tokens", headers=origin).json()["token"]
        paired = client.post("/api/endpoints/pair", json={"token": token, "name": "Device"}).json()
        endpoint = paired["endpoint_id"]
        original = app.state.application
        app.state.application = replace(
            original, mutation_authorization=MutationAuthorizationPolicy.read_only()
        )
        assert (
            client.post(
                f"/api/endpoints/{endpoint}/operation",
                headers=origin,
                json={"operation": "browser.open", "arguments": {"url": "http://fixture.test"}},
            ).status_code
            == 403
        )
        app.state.application = original
        assert client.post(f"/api/endpoints/{endpoint}/chat").status_code == 403
        session = client.post(f"/api/endpoints/{endpoint}/chat", headers=origin).json()
        session_id = session["session_id"]
        assert session["surface_kind"] == "device" and session["endpoint_id"] == endpoint
        assert session["project_id"] is None and session["mutation_mode"] == "read_only"
        assert (
            client.post(f"/api/endpoints/{endpoint}/chat", headers=origin).json()["session_id"]
            == session_id
        )
        ordinary = client.post("/api/sessions").json()["session_id"]
        assert [row["session_id"] for row in client.get("/api/sessions").json()] == [ordinary]
        changed = client.patch(
            f"/api/sessions/{session_id}/mutation-mode", json={"mutation_mode": "confirm"}
        ).json()
        assert changed["mutation_mode"] == "confirm" and changed["endpoint_id"] == endpoint
        assert client.get(f"/api/sessions/{ordinary}").json()["mutation_mode"] == "read_only"
        assert (
            client.post(
                f"/api/sessions/{session_id}/attachments", files={"file": ("secret.txt", b"secret")}
            ).status_code
            == 409
        )
        assert client.delete(f"/api/sessions/{session_id}").status_code == 409
        assert (
            client.post(
                f"/api/endpoints/{endpoint}/forget", headers=origin, json={"confirmed": False}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/endpoints/{endpoint}/end", headers={"Authorization": "Bearer wrong"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                f"/api/endpoints/{endpoint}/end",
                headers={"Authorization": "Bearer " + paired["credential"]},
            ).status_code
            == 200
        )
        assert not app.state.application.endpoints.store.authenticate(**paired)
        assert (
            client.post(
                f"/api/endpoints/{endpoint}/forget", headers=origin, json={"confirmed": True}
            ).status_code
            == 200
        )
        assert client.get(f"/api/sessions/{session_id}").status_code == 404
        assert client.get("/api/endpoints").json() == []
        assert client.get(f"/api/sessions/{ordinary}").status_code == 200


def test_device_chat_same_runtime_offline_and_cannot_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORION_ENDPOINTS", "1")

    async def scenario() -> None:
        backend = ScriptedBackend([])
        application = build_application(tmp_path / "db", backend)
        endpoints, store = application.endpoints.store, application.store
        first = endpoints.pair(endpoints.token()["token"], "Bound device")["endpoint_id"]
        other = endpoints.pair(endpoints.token()["token"], "Other device")["endpoint_id"]
        ordinary = store.create_session()
        project = store.create_project("Project")
        project_session = store.create_session(project_id=project["project_id"])
        store.append_timeline(ordinary, None, "user_message", {"content": "ordinary secret"})
        store.append_timeline(project_session, None, "user_message", {"content": "project secret"})
        device = endpoints.device_chat(first, "local", "local")
        store.set_session_mutation_mode(device, MutationMode.AUTO)
        store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
        backend.turns = [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="read",
                        tool_name="endpoint.system.inspect",
                        arguments={"target_ref": first},
                    ),
                )
            ),
            *[
                ModelTurn(assistant=AssistantMessage(content="Endpoint is offline."))
                for _ in range(4)
            ],
        ]
        await application.runtime.submit(device, "Inspect this device")
        serialized = json.dumps([item.model_dump(mode="json") for item in store.timeline(device)])
        assert (
            "offline" in serialized
            and "ordinary secret" not in serialized
            and "project secret" not in serialized
        )
        context = " ".join(message.content for message in backend.calls[0][0])
        assert first in context and "Bound device" in context
        assert "ordinary secret" not in context and "project secret" not in context
        scope = application.runtime._runtime_scope(device)
        assert scope.endpoint_id == first and scope.project_id is None and not scope.attachment_ids
        runner = ToolRunner(application.registry)
        for operation in ("endpoint.system.inspect", "endpoint.file.delete"):
            args = {"target_ref": other, **({"path": "/file"} if "delete" in operation else {})}
            result = await runner.run_async(
                ModelToolCall(call_id="escape", tool_name=operation, arguments=args), scope
            )
            assert result.error.code == "operation_blocked"
        discovered = await runner.run_async(
            ModelToolCall(call_id="list", tool_name="endpoint.list", arguments={}), scope
        )
        assert [row["endpoint_id"] for row in discovered.data["endpoints"]] == [first]
        scheduled = application.scheduler.create(
            scope,
            TaskInput(
                prompt="Inspect this endpoint read-only",
                schedule_kind="once",
                run_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
            ),
        )
        task_session = scheduled["execution_session_id"]
        assert application.runtime._runtime_scope(task_session).endpoint_id == first
        assert task_session not in {
            row["session_id"] for row in store.session_summaries("local", "local")
        }
        active = store.create_request(task_session)
        with pytest.raises(RuntimeError, match="active_request"):
            endpoints.forget(first)
        assert store.session_exists(device)
        store.complete_request(active, "cancelled")
        with pytest.raises(ValueError):
            store.create_session(project_id=project["project_id"], endpoint_id=first)
        endpoints.forget(first)
        assert not store.session_exists(task_session)
        assert store.session_exists(ordinary) and store.session_exists(project_session)
        await application.endpoints.close()
        store.close()

    asyncio.run(scenario())
