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
        "request.started",
        "model.started",
        "model.completed",
        "tool.started",
        "tool.completed",
        "model.started",
        "model.completed",
        "request.completed",
    ]
    assert events[0]["payload"]["request_id"] == response.json()["request_id"]


@pytest.mark.anyio
async def test_api_streams_public_runtime_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Streamed."))])
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
    assert '"type": "request.completed"' in response.text
