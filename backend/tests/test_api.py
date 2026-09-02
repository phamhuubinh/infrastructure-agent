from __future__ import annotations

import httpx
import pytest
from conftest import ScriptedBackend

from orion.api.app import create_app
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn
from orion.tool_runtime.registry import EXPAND_TOOL_NAME


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
async def test_api_hides_unverified_citation_details_from_the_user(tmp_path) -> None:  # type: ignore[no-untyped-def]
    invalid = ModelTurn(
        assistant=AssistantMessage(
            content="Answer [[source:provider-secret-citation]]",
            citation_source_ref_ids=("provider-secret-citation",),
        )
    )
    backend = ScriptedBackend([invalid, invalid])
    app = create_app(tmp_path / "orion.db", backend)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await _configure(client)
        session = (await client.post("/api/sessions")).json()["session_id"]
        response = await client.post(f"/api/sessions/{session}/messages", json={"content": "Hello"})
        timeline = (await client.get(f"/api/sessions/{session}/timeline")).json()

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Orion could not verify the response against available sources."
    )
    assert "provider-secret-citation" not in response.text
    assert timeline[-1]["payload"]["error_kind"] == "unavailable_source"


@pytest.mark.anyio
async def test_session_summaries_are_scope_safe_durable_and_sidebar_ready(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "sessions.db"
    app = create_app(database, ScriptedBackend([]))
    store = app.state.application.store
    assert store.session_summaries("local", "local") == []
    first = store.create_session("local", "local")
    project = app.state.application.projects.create("Scoped project")
    project_session = store.create_session("local", "local", project["project_id"])
    foreign_principal = store.create_session("other", "local")
    foreign_workspace = store.create_session("local", "other")
    store.append_timeline(first, None, "user_message", {"content": "  First   persisted chat  "})
    store.append_timeline(project_session, None, "user_message", {"content": "Project history"})
    store.append_timeline(foreign_principal, None, "user_message", {"content": "Do not expose"})
    store.append_timeline(foreign_workspace, None, "user_message", {"content": "Also private"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        listed = await client.get(
            "/api/sessions",
            params={"principal_id": "other", "workspace_id": "other", "project_id": "forged"},
        )
        foreign_session = await client.get(f"/api/sessions/{foreign_principal}")

    assert listed.status_code == 200
    assert foreign_session.status_code == 404
    summaries = listed.json()
    assert {item["session_id"] for item in summaries} == {first, project_session}
    assert summaries[0]["last_activity_at"] >= summaries[1]["last_activity_at"]
    normal = next(item for item in summaries if item["session_id"] == first)
    project_summary = next(item for item in summaries if item["session_id"] == project_session)
    assert normal["title"] == "First persisted chat"
    assert project_summary["project_id"] == project["project_id"]
    assert all("Do not expose" not in str(item) for item in summaries)

    store.close()
    restarted = create_app(database, ScriptedBackend([]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        after_restart = await client.get("/api/sessions")
    assert {item["session_id"] for item in after_restart.json()} == {first, project_session}


def test_session_summaries_have_a_fixed_server_side_bound(tmp_path) -> None:
    store = create_app(tmp_path / "sessions.db", ScriptedBackend([])).state.application.store
    for _ in range(101):
        store.create_session("local", "local")

    assert len(store.session_summaries("local", "local", limit=10_000)) == 100


@pytest.mark.anyio
async def test_health_is_a_cheap_process_check_and_integration_status_routes_are_absent(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        health = await client.get("/api/health")
        internet = await client.get("/api/integrations/internet")
        linux = await client.get("/api/integrations/linux")

    assert health.json() == {"status": "ok", "identity": "orion"}
    assert internet.status_code == 404
    assert linux.status_code == 404


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
async def test_api_exposes_calculator_activity_as_runtime_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="expand",
                        tool_name=EXPAND_TOOL_NAME,
                        arguments={"tool_names": ["calculator.evaluate"]},
                    ),
                )
            ),
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
            files={"file": ("private.txt", b"private document", "text/plain")},
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
    assert attachment.json()["status"] == "ready"
    assert own_status.status_code == 200
    assert foreign_status.status_code == 404
    assert foreign_delete.status_code == 404
    assert unscoped_status.status_code == 404
    assert own_delete.status_code == 200
    assert remote_status.status_code == 404


@pytest.mark.anyio
async def test_document_upload_limit_is_enforced_before_ingestion(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ORION_MAX_DOCUMENT_UPLOAD_BYTES", "8")
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        session = (await client.post("/api/sessions")).json()["session_id"]
        response = await client.post(
            f"/api/sessions/{session}/attachments",
            files={"file": ("too-large.txt", b"123456789", "text/plain")},
        )

    assert response.status_code == 413
    assert "8-byte upload limit" in response.json()["detail"]
    assert app.state.application.knowledge.list_documents(
        app.state.application.runtime._scope(session)  # type: ignore[attr-defined]
    ) == []


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
            files={"file": ("requirements.txt", b"A-only fact", "text/plain")},
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
