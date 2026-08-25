from __future__ import annotations

import httpx
import pytest
from conftest import ScriptedBackend

from orion.api.app import create_app
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn


async def _configure(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/models",
        json={
            "provider_type": "openai_compatible",
            "base_url": "http://model.test/v1",
            "model_id": "fake",
        },
    )
    assert response.status_code == 201


@pytest.mark.anyio
async def test_api_direct_chat_has_no_tool_selector(tmp_path) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Hello."))])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(tmp_path / "orion.db", backend)),
        base_url="http://test",
    ) as client:
        await _configure(client)
        session = (await client.post("/api/sessions")).json()["session_id"]
        response = await client.post(f"/api/sessions/{session}/messages", json={"content": "Hello"})
        schema = (await client.get("/openapi.json")).json()

    assert response.status_code == 200
    assert response.json()["assistant_content"] == "Hello."
    assert "enabled_tools" not in str(schema)
    assert "handler_key" not in str(schema)


@pytest.mark.anyio
async def test_api_exposes_calculator_activity_as_runtime_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="calc-1",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "9 - 4"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="5")),
        ]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(tmp_path / "orion.db", backend)),
        base_url="http://test",
    ) as client:
        await _configure(client)
        session = (await client.post("/api/sessions")).json()["session_id"]
        response = await client.post(
            f"/api/sessions/{session}/messages", json={"content": "Calculate 9-4"}
        )
        events = (await client.get(f"/api/requests/{response.json()['request_id']}/events")).json()

    assert response.status_code == 200
    assert [event["type"] for event in events] == [
        "request.accepted",
        "model.started",
        "model.completed",
        "tool.started",
        "tool.completed",
        "model.resumed",
        "model.started",
        "model.completed",
        "assistant.message",
        "request.completed",
    ]
    assert events[0]["payload"]["request_id"] == response.json()["request_id"]


@pytest.mark.anyio
async def test_api_streams_public_runtime_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [ModelTurn(assistant=AssistantMessage(content="Streamed."))],
        deltas=[["Stream", "ed."]],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(tmp_path / "orion.db", backend)),
        base_url="http://test",
    ) as client:
        await _configure(client)
        session = (await client.post("/api/sessions")).json()["session_id"]
        response = await client.post(
            f"/api/sessions/{session}/messages/stream", json={"content": "Hello"}
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.count('"type": "assistant.delta"') == 2
    assert '"type": "assistant.message"' in response.text
    assert '"type": "request.completed"' in response.text


@pytest.mark.anyio
async def test_document_status_and_delete_are_session_scoped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend([])
    app = create_app(tmp_path / "orion.db", backend)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first_session = (await client.post("/api/sessions")).json()["session_id"]
        second_session = (await client.post("/api/sessions")).json()["session_id"]
        attachment = await client.post(
            f"/api/sessions/{first_session}/attachments",
            json={"name": "private.txt", "content": "private document"},
        )
        document_id = attachment.json()["document"]["document_id"]

        own_status = await client.get(f"/api/sessions/{first_session}/documents/{document_id}")
        foreign_status = await client.get(f"/api/sessions/{second_session}/documents/{document_id}")
        foreign_delete = await client.delete(
            f"/api/sessions/{second_session}/documents/{document_id}"
        )
        unscoped_status = await client.get(f"/api/documents/{document_id}")
        own_delete = await client.delete(f"/api/sessions/{first_session}/documents/{document_id}")
        remote_session = app.state.application.store.create_session("remote", "remote")
        remote_document = app.state.application.knowledge.attach(
            remote_session, "remote.txt", b"not local principal data"
        )
        remote_status = await client.get(
            f"/api/sessions/{remote_session}/documents/{remote_document.document.document_id}"
        )

    assert attachment.status_code == 201
    assert own_status.status_code == 200
    assert foreign_status.status_code == 404
    assert foreign_delete.status_code == 404
    assert unscoped_status.status_code == 404
    assert own_delete.status_code == 200
    assert remote_status.status_code == 404
