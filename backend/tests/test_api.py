from __future__ import annotations

import httpx
import pytest
from conftest import ScriptedBackend

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn
from orion.integrations import SearxngInternetClient


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
async def test_api_reports_optional_internet_integration_without_exposing_secrets(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(tmp_path / "orion.db", ScriptedBackend([]))),
        base_url="http://test",
    ) as client:
        integration = await client.get("/api/integrations/internet")
        health = await client.get("/api/health")

    assert integration.json() == {
        "status": "unconfigured",
        "provider": None,
        "endpoint": None,
        "message": "Internet search is not configured. Set ORION_INTERNET_SEARCH_URL to enable it.",
    }
    assert health.json()["internet"]["status"] == "unconfigured"
    assert "key" not in str(integration.json()).lower()


@pytest.mark.anyio
async def test_packaged_ui_serves_root_assets_and_client_routes_without_capturing_api(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    frontend = tmp_path / "ui"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "_shell.html").write_text(
        "<!doctype html><html><head><title>Orion</title></head><body>Orion UI</body></html>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('orion');", encoding="utf-8")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=create_app(tmp_path / "orion.db", ScriptedBackend([]), ui_directory=frontend)
        ),
        base_url="http://test",
    ) as client:
        root = await client.get("/")
        asset = await client.get("/assets/app.js")
        route = await client.get("/projects/example")
        health = await client.get("/api/health")
        missing_api = await client.get("/api/not-a-route")

    assert root.status_code == 200 and "<title>Orion</title>" in root.text
    assert asset.status_code == 200 and asset.text == "console.log('orion');"
    assert route.status_code == 200 and "Orion UI" in route.text
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert health.json()["identity"] == "orion"
    assert missing_api.status_code == 404 and "Orion UI" not in missing_api.text


@pytest.mark.anyio
async def test_api_distinguishes_healthy_and_unhealthy_internet_configuration(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    healthy_application = build_application(
        tmp_path / "healthy.db",
        ScriptedBackend([]),
        internet_client=SearxngInternetClient(
            "https://search.test/api",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"results": []})
            ),
        ),
    )
    unhealthy_application = build_application(
        tmp_path / "unhealthy.db",
        ScriptedBackend([]),
        internet_client=SearxngInternetClient(
            "https://search.test/api",
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(application=healthy_application)),
        base_url="http://test",
    ) as healthy_client:
        healthy = await healthy_client.get("/api/integrations/internet")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(application=unhealthy_application)),
        base_url="http://test",
    ) as unhealthy_client:
        unhealthy = await unhealthy_client.get("/api/integrations/internet")

    assert healthy.json()["status"] == "healthy"
    assert unhealthy.json()["status"] == "unhealthy"
    assert (
        unhealthy.json()["message"]
        == "Configured Internet search integration is currently unavailable."
    )


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


@pytest.mark.anyio
async def test_project_api_binds_sessions_and_documents_without_message_project_ids(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend([])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(tmp_path / "orion.db", backend)),
        base_url="http://test",
    ) as client:
        project = await client.post(
            "/api/projects",
            json={
                "name": "Capacity",
                "description": "Sizing",
                "instructions": "Use the durable facts.",
                "metadata": {"environment": "local"},
            },
        )
        project_id = project.json()["project_id"]
        session = await client.post(f"/api/projects/{project_id}/sessions")
        document = await client.post(
            f"/api/projects/{project_id}/documents",
            json={"name": "requirements.txt", "content": "A-only fact"},
        )
        document_id = document.json()["document"]["document_id"]
        status = await client.get(f"/api/projects/{project_id}/documents/{document_id}")
        forged_message = await client.post(
            f"/api/sessions/{session.json()['session_id']}/messages",
            json={"content": "hello", "project_id": "forged"},
        )
        schema = (await client.get("/openapi.json")).json()

    assert project.status_code == 201
    assert session.status_code == 201
    assert session.json()["project_id"] == project_id
    assert document.status_code == 201
    assert status.json()["document"]["source"] == {"kind": "project", "source_id": project_id}
    assert forged_message.status_code == 422
    assert "enabled_tools" not in str(schema)
