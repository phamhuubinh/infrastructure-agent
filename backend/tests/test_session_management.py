from __future__ import annotations

import sqlite3

import httpx
import pytest
from conftest import ScriptedBackend

from orion.api.app import create_app


@pytest.mark.anyio
async def test_session_title_is_migrated_persisted_and_scope_safe(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, principal_id TEXT, workspace_id TEXT, "
        "project_id TEXT, created_at TEXT NOT NULL)"
    )
    connection.commit()
    connection.close()
    app = create_app(database, ScriptedBackend([]))
    store = app.state.application.store
    session = store.create_session()
    project = app.state.application.projects.create("Project")
    project_session = store.create_session(project_id=project["project_id"])
    store.append_timeline(session, None, "user_message", {"content": "  Derived   title  "})
    timeline_before = store.timeline(project_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        derived = await client.get("/api/sessions")
        renamed = await client.patch(
            f"/api/sessions/{project_session}", json={"title": "  Tiêu đề dự án  "}
        )
        listed = await client.get("/api/sessions")
        empty = await client.patch(f"/api/sessions/{session}", json={"title": "   "})
        too_long = await client.patch(f"/api/sessions/{session}", json={"title": "x" * 121})
        missing = await client.patch("/api/sessions/missing", json={"title": "Missing"})

    assert (
        next(item for item in derived.json() if item["session_id"] == session)["title"]
        == "Derived title"
    )
    assert renamed.status_code == 200
    assert renamed.json() == {
        "session_id": project_session,
        "project_id": project["project_id"],
        "title": "Tiêu đề dự án",
    }
    assert (
        next(item for item in listed.json() if item["session_id"] == project_session)["title"]
        == "Tiêu đề dự án"
    )
    assert store.timeline(project_session) == timeline_before
    assert empty.status_code == 422
    assert too_long.status_code == 422
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_deleting_session_removes_owned_data_but_preserves_project_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    store, knowledge = app.state.application.store, app.state.application.knowledge
    session = store.create_session()
    request = store.create_request(session, status="completed")
    store.emit_event(request, "request.completed", {})
    store.append_timeline(session, request, "user_message", {"content": "Delete me"})
    uploaded = knowledge.attach(session, "session.txt", b"session-only")
    document_id = uploaded.document.document_id
    blob_id = store.document(document_id)["blob_id"]  # type: ignore[index]
    project = app.state.application.projects.create("Keep project")
    sibling = store.create_session(project_id=project["project_id"])
    project_document = knowledge.attach_project(project["project_id"], "project.txt", b"keep")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        deleted = await client.delete(f"/api/sessions/{session}")
        summaries = await client.get("/api/sessions")
        identity = await client.get(f"/api/sessions/{session}")
        timeline = await client.get(f"/api/sessions/{session}/timeline")

    assert deleted.status_code == 204
    assert session not in {item["session_id"] for item in summaries.json()}
    assert identity.status_code == 404 and timeline.status_code == 404
    assert store.request(request) is None
    assert store.events(request) == []
    assert store.document(document_id) is None
    assert store.document_segments(document_id) == []
    assert store.document_ingestion_events(document_id) == []
    assert not (tmp_path / "blobs" / blob_id).exists()
    assert app.state.application.projects.get(project["project_id"]) is not None
    assert store.session_identity(sibling)["project_id"] == project["project_id"]  # type: ignore[index]
    assert store.document(project_document.document.document_id) is not None


@pytest.mark.anyio
async def test_deleting_session_with_running_request_returns_conflict(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    session = app.state.application.store.create_session()
    app.state.application.store.create_request(session, status="queued")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.delete(f"/api/sessions/{session}")
    assert response.status_code == 409
    assert "finish or be cancelled" in response.json()["detail"]
