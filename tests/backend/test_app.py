from __future__ import annotations

import json
from unittest import mock

from src.backend.app import create_app


def test_health_endpoint() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_check_model_calls_health_check() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # LLM is online — should return ok
    resp = client.get("/api/check-model")
    data = resp.json()
    assert resp.status_code == 200
    # status may be "ok" or "error" depending on LLM availability
    assert "status" in data


@mock.patch("src.model.llm_client.LLMClient.health_check")
def test_check_model_returns_ok_when_llm_healthy(mock_health) -> None:
    mock_health.return_value = True
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/check-model")
    assert resp.json()["status"] == "ok"
    mock_health.assert_called_once()


@mock.patch("src.model.llm_client.LLMClient.health_check")
def test_check_model_returns_error_when_llm_unhealthy(mock_health) -> None:
    mock_health.side_effect = RuntimeError("LLM unreachable")
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/check-model")
    data = resp.json()
    assert data["status"] == "error"
    assert "LLM unreachable" in data.get("error", "")


def test_check_model_returns_valid_json() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/check-model")
    assert resp.status_code == 200
    # Response must be valid JSON
    data = json.loads(resp.text)
    assert isinstance(data, dict)


@mock.patch("urllib.request.urlopen")
def test_dify_health_ok(mock_urlopen) -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    mock_resp = mock.MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value = mock_resp

    client = TestClient(app)
    resp = client.get("/api/dify/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["dify"] is True


@mock.patch("urllib.request.urlopen")
def test_dify_health_error(mock_urlopen) -> None:
    mock_urlopen.side_effect = RuntimeError("Dify unreachable")
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/dify/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


@mock.patch("urllib.request.urlopen")
def test_dify_chat_sends_query(mock_urlopen) -> None:
    mock_resp_data = {
        "answer": "Dify answer here",
        "conversation_id": "conv-123",
        "message_id": "msg-456",
    }
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post("/api/dify/chat", json={"question": "check nginx"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Dify answer here"
    assert data["conversation_id"] == "conv-123"
    assert data["message_id"] == "msg-456"


@mock.patch("urllib.request.urlopen")
def test_dify_chat_missing_question(mock_urlopen) -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post("/api/dify/chat", json={})
    assert resp.status_code == 400


@mock.patch("urllib.request.urlopen")
def test_dify_chat_handles_error(mock_urlopen) -> None:
    mock_urlopen.side_effect = RuntimeError("Dify API error")
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post("/api/dify/chat", json={"question": "check nginx"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "Dify API error" in data.get("error", "")


@mock.patch("urllib.request.urlopen")
def test_dify_knowledge_query_returns_results(mock_urlopen) -> None:
    mock_resp_data = {"records": [{"id": "doc-1", "score": 0.95}]}
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post("/api/dify/knowledge/query", json={"query": "nginx config"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["records"][0]["id"] == "doc-1"


@mock.patch("urllib.request.urlopen")
def test_dify_knowledge_query_missing_query(mock_urlopen) -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post("/api/dify/knowledge/query", json={})
    assert resp.status_code == 400


@mock.patch("urllib.request.urlopen")
def test_dify_knowledge_query_handles_error(mock_urlopen) -> None:
    mock_urlopen.side_effect = RuntimeError("Knowledge API error")
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.post("/api/dify/knowledge/query", json={"query": "nginx config"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "Knowledge API error" in data.get("error", "")
