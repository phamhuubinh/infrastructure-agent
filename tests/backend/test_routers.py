from __future__ import annotations

import json
from unittest import mock

import pytest

from src.backend.app import create_app


@pytest.fixture
def app():
    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
        mock.patch("urllib.request.urlopen", side_effect=RuntimeError("no rag")),
    ):
        app, _, _ = create_app(database_url="")
    from fastapi.testclient import TestClient

    return TestClient(app)


# ── Sessions ──────────────────────────────────────────────────────────


def test_list_sessions_empty(app):
    resp = app.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


def test_list_sessions_with_data(app, tmp_path):
    from fastapi.testclient import TestClient

    sess_dir = tmp_path / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "abc123.json").write_text(
        json.dumps({"session_id": "abc123", "title": "Test Session", "messages": []})
    )
    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        app_obj.state.deps.sessions_dir = str(sess_dir)
        client = TestClient(app_obj)
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) >= 1
        ids = [s["id"] for s in data["sessions"]]
        assert "abc123" in ids


def test_delete_session_not_found(app):
    resp = app.delete("/api/sessions/nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_delete_session_success(app, tmp_path):
    from fastapi.testclient import TestClient

    sess_dir = tmp_path / "sessions"
    sess_dir.mkdir(parents=True)
    sess_file = sess_dir / "delme.json"
    sess_file.write_text(
        json.dumps({"session_id": "delme", "title": "Delete Me", "messages": []})
    )
    with mock.patch("src.backend.dependencies._get_dsn", return_value=None):
        app_obj, _, _ = create_app(database_url="")
        app_obj.state.deps.sessions_dir = str(sess_dir)
        client = TestClient(app_obj)
        resp = client.delete("/api/sessions/delme")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert not sess_file.exists()


def test_rename_session_missing_title(app):
    resp = app.patch("/api/sessions/abc", json={})
    assert resp.status_code == 400
    assert "title is required" in resp.json()["detail"].lower()


def test_rename_session_not_found(app):
    resp = app.patch("/api/sessions/nonexistent", json={"title": "New Title"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_rename_session_success(app, tmp_path):
    from fastapi.testclient import TestClient

    sess_dir = tmp_path / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "rename_me.json").write_text(
        json.dumps({"session_id": "rename_me", "title": "Old Title", "messages": []})
    )
    with mock.patch("src.backend.dependencies._get_dsn", return_value=None):
        app_obj, _, _ = create_app(database_url="")
        app_obj.state.deps.sessions_dir = str(sess_dir)
        client = TestClient(app_obj)
        resp = client.patch("/api/sessions/rename_me", json={"title": "New Title"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "renamed"
        data = json.loads((sess_dir / "rename_me.json").read_text())
        assert data["title"] == "New Title"


# ── Knowledge ─────────────────────────────────────────────────────────


def test_knowledge_health_no_rag(app):
    resp = app.get("/api/knowledge/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


@mock.patch("urllib.request.urlopen")
def test_knowledge_health_success(mock_urlopen):
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
    mock_urlopen.return_value = mock_resp
    from fastapi.testclient import TestClient

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        app_obj.state.deps.rag_service_url = "http://fake-rag:8080"
        client = TestClient(app_obj)
        resp = client.get("/api/knowledge/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_knowledge_query_missing_query(app):
    resp = app.post("/api/knowledge/query", json={})
    assert resp.status_code == 400
    assert "query is required" in resp.json()["detail"].lower()


def test_knowledge_query_empty_query(app):
    resp = app.post("/api/knowledge/query", json={"query": "   "})
    assert resp.status_code == 400


def test_knowledge_query_success():
    mock_resp = mock.MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps(
        {"results": [{"text": "ansible docs"}], "status": "ok"}
    ).encode("utf-8")
    from fastapi.testclient import TestClient

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
        mock.patch(
            "src.backend.routers.knowledge.urllib.request.urlopen"
        ) as mock_urlopen,
    ):
        mock_urlopen.return_value = mock_resp
        app_obj, _, _ = create_app(database_url="")
        app_obj.state.deps.rag_service_url = "http://fake-rag:8080"
        client = TestClient(app_obj)
        resp = client.post("/api/knowledge/query", json={"query": "ansible"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["results"]) == 1


# ── Documents ─────────────────────────────────────────────────────────


def test_document_upload_missing_content(app):
    resp = app.post("/api/documents/upload", json={"filename": "test.bin"})
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["filename"] == "test.bin"
    assert data["content_type"] == "application/octet-stream"


def test_document_upload_with_content(app, tmp_path):
    from fastapi.testclient import TestClient

    docs_dir = tmp_path / ".orion" / "documents"
    docs_dir.mkdir(parents=True)
    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.backend.document_service._STORAGE_DIR", docs_dir),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        app_obj.state.deps.rag_service_url = None
        client = TestClient(app_obj)
        resp = client.post(
            "/api/documents/upload",
            json={
                "filename": "hello.txt",
                "content": "Hello, World!",
                "content_type": "text/plain",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "hello.txt"
        assert data["size_bytes"] == len("Hello, World!")
        stored_file = docs_dir / f"{data['id']}.txt"
        assert stored_file.read_text() == "Hello, World!"


def test_document_list_empty(app):
    resp = app.get("/api/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert "documents" in data
    assert isinstance(data["documents"], list)


def test_document_get_not_found(app):
    resp = app.get("/api/documents/nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_document_get_success(app, tmp_path):
    from fastapi.testclient import TestClient

    docs_dir = tmp_path / ".orion" / "documents"
    docs_dir.mkdir(parents=True)
    doc_id = "testdoc123"
    (docs_dir / f"{doc_id}.txt").write_text("file content")

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.backend.document_service._STORAGE_DIR", docs_dir),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        client = TestClient(app_obj)

        resp = client.get(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id
        assert resp.json()["filename"] == f"{doc_id}.txt"


def test_document_download_not_found(app):
    resp = app.get("/api/documents/nonexistent/download")
    assert resp.status_code == 404


def test_document_download_success(app, tmp_path):
    from fastapi.testclient import TestClient

    docs_dir = tmp_path / ".orion" / "documents"
    docs_dir.mkdir(parents=True)
    doc_id = "dl_doc"
    (docs_dir / f"{doc_id}.txt").write_text("downloadable content")

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.backend.document_service._STORAGE_DIR", docs_dir),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        client = TestClient(app_obj)

        resp = client.get(f"/api/documents/{doc_id}/download")
        assert resp.status_code == 200
        assert resp.text == "downloadable content"
        assert "attachment" in resp.headers["content-disposition"]


def test_document_delete_not_found(app):
    resp = app.delete("/api/documents/nonexistent")
    assert resp.status_code == 404


def test_document_delete_success(app, tmp_path):
    from fastapi.testclient import TestClient

    docs_dir = tmp_path / ".orion" / "documents"
    docs_dir.mkdir(parents=True)
    doc_id = "del_doc"
    doc_path = docs_dir / f"{doc_id}.txt"
    doc_path.write_text("to be deleted")

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.backend.document_service._STORAGE_DIR", docs_dir),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        client = TestClient(app_obj)

        resp = client.delete(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert not doc_path.exists()


# ── Query ──────────────────────────────────────────────────────────────


def test_query_missing_question(app):
    resp = app.post("/api/query", json={})
    assert resp.status_code == 400
    assert "question is required" in resp.json()["detail"].lower()


def test_query_empty_question(app):
    resp = app.post("/api/query", json={"question": "   "})
    assert resp.status_code == 400


def test_query_success(app):
    from fastapi.testclient import TestClient

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
    mock_agent = mock.MagicMock()
    mock_agent.run_with_steps.return_value = {
        "steps": [{"tool": "ping", "result": "ok"}],
        "response": "Server is healthy",
    }
    app_obj.state.deps.agent = mock_agent
    client = TestClient(app_obj)
    resp = client.post(
        "/api/query",
        json={"question": "Is server sv1 healthy?", "session_id": "test-sess"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assessment"] == "Server is healthy"
    assert len(data["steps"]) == 1


def test_query_generates_session_id_when_not_provided(app):
    from fastapi.testclient import TestClient

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        mock_agent = mock.MagicMock()
        mock_agent.run_with_steps.return_value = {
            "steps": [],
            "response": "ok",
        }
        app_obj.state.deps.agent = mock_agent
        client = TestClient(app_obj)
        resp = client.post("/api/query", json={"question": "test"})
        assert resp.status_code == 200
        assert len(app_obj.state.deps.web_sessions) == 1


# ── Service Status ────────────────────────────────────────────────────


def test_service_status_structure(app):
    resp = app.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "components" in data
    assert "app" in data["components"]
    assert "database" in data["components"]
    assert "llm" in data["components"]
    assert "rag" in data["components"]
    assert "timestamp" in data


def test_service_status_degraded(app):
    resp = app.get("/api/status")
    data = resp.json()
    assert data["components"]["rag"]["status"] == "error"
    assert data["status"] == "degraded"


# ── Documents (with session_id filter) ───────────────────────────────


def test_document_list_filtered_by_session_id(app, tmp_path):
    from fastapi.testclient import TestClient

    docs_dir = tmp_path / ".orion" / "documents"
    docs_dir.mkdir(parents=True)
    (docs_dir / "doc1.txt").write_text("session1 doc")
    (docs_dir / "doc2.txt").write_text("session2 doc")

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.backend.document_service._STORAGE_DIR", docs_dir),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        client = TestClient(app_obj)
        resp = client.get("/api/documents", params={"session_id": "sess1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data


def test_document_upload_with_session_id(app, tmp_path):
    from fastapi.testclient import TestClient

    docs_dir = tmp_path / ".orion" / "documents"
    docs_dir.mkdir(parents=True)
    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.backend.document_service._STORAGE_DIR", docs_dir),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        app_obj.state.deps.rag_service_url = None
        client = TestClient(app_obj)
        resp = client.post(
            "/api/documents/upload",
            json={
                "filename": "sess_doc.txt",
                "content": "doc content",
                "session_id": "sess-123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-123"


def test_document_download_file_not_on_disk(app, tmp_path):
    from fastapi.testclient import TestClient

    docs_dir = tmp_path / ".orion" / "documents"
    docs_dir.mkdir(parents=True)
    doc_id = "missing_file"
    (docs_dir / f"{doc_id}.txt").write_text("content")

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.backend.document_service._STORAGE_DIR", docs_dir),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
    ):
        app_obj, _, _ = create_app(database_url="")
        client = TestClient(app_obj)
        doc_path = docs_dir / f"{doc_id}.txt"
        doc_path.unlink()
        resp = client.get(f"/api/documents/{doc_id}/download")
        assert resp.status_code == 404


# ── Sessions (DB mode) ───────────────────────────────────────────────


@mock.patch(
    "src.backend.db._get_dsn",
    return_value="postgresql://user:pass@localhost:5432/orion",
)
@mock.patch("src.backend.db._import_driver")
@mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True)
def test_sessions_list_db_mode(mock_health, mock_driver, mock_dsn):
    mock_conn = mock.MagicMock()
    mock_cursor = mock.MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_driver.connect.return_value = mock_conn
    mock_driver.return_value = (mock_driver, None)

    app_obj, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app_obj)
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []


@mock.patch(
    "src.backend.db._get_dsn",
    return_value="postgresql://user:pass@localhost:5432/orion",
)
@mock.patch("src.backend.db._import_driver")
@mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True)
def test_sessions_delete_db_mode(mock_health, mock_driver, mock_dsn):
    mock_conn = mock.MagicMock()
    mock_cursor = mock.MagicMock()
    mock_cursor.rowcount = 1
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_driver.connect.return_value = mock_conn
    mock_driver.return_value = (mock_driver, None)

    app_obj, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app_obj)
    resp = client.delete("/api/sessions/test-sess")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@mock.patch(
    "src.backend.db._get_dsn",
    return_value="postgresql://user:pass@localhost:5432/orion",
)
@mock.patch("src.backend.db._import_driver")
@mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True)
def test_sessions_rename_db_mode(mock_health, mock_driver, mock_dsn):
    mock_conn = mock.MagicMock()
    mock_cursor = mock.MagicMock()
    mock_cursor.rowcount = 1
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_driver.connect.return_value = mock_conn
    mock_driver.return_value = (mock_driver, None)

    app_obj, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app_obj)
    resp = client.patch("/api/sessions/test-sess", json={"title": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"


# ── Knowledge (error handling) ───────────────────────────────────────


def test_knowledge_query_rag_error(app):
    with mock.patch(
        "src.backend.routers.knowledge.urllib.request.urlopen",
        side_effect=RuntimeError("connection refused"),
    ):
        resp = app.post("/api/knowledge/query", json={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"


def test_knowledge_health_connected_but_no_rag(app):
    with mock.patch(
        "src.backend.routers.knowledge.urllib.request.urlopen",
        side_effect=RuntimeError("timeout"),
    ):
        resp = app.get("/api/knowledge/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
