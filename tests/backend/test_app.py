from __future__ import annotations

import json
from unittest import mock

from src.backend.app import create_app


@mock.patch("src.backend.dependencies._get_dsn", return_value=None)
def test_health_endpoint(mock_dsn: mock.MagicMock) -> None:
    app, _, _ = create_app(database_url="")
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@mock.patch("src.backend.dependencies._get_dsn", return_value=None)
def test_check_model_calls_health_check(mock_dsn: mock.MagicMock) -> None:
    app, _, _ = create_app(database_url="")
    from fastapi.testclient import TestClient

    client = TestClient(app)

    resp = client.get("/api/check-model")
    data = resp.json()
    assert resp.status_code == 200
    assert "status" in data


@mock.patch("src.backend.dependencies._get_dsn", return_value=None)
@mock.patch("src.agent.deterministic_agent.DeterministicAgent.health_check")
def test_check_model_returns_ok_when_llm_healthy(
    mock_health: mock.MagicMock, mock_dsn: mock.MagicMock
) -> None:
    mock_health.return_value = True
    app, _, _ = create_app(database_url="")
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/check-model")
    assert resp.json()["status"] == "ok"
    mock_health.assert_called_once()


@mock.patch("src.backend.dependencies._get_dsn", return_value=None)
@mock.patch("src.agent.deterministic_agent.DeterministicAgent.health_check")
def test_check_model_returns_error_when_llm_unhealthy(
    mock_health: mock.MagicMock, mock_dsn: mock.MagicMock
) -> None:
    mock_health.side_effect = RuntimeError("LLM unreachable")
    app, _, _ = create_app(database_url="")
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/check-model")
    data = resp.json()
    assert data["status"] == "error"
    assert "LLM unreachable" in data.get("error", "")


@mock.patch("src.backend.dependencies._get_dsn", return_value=None)
def test_check_model_returns_valid_json(mock_dsn: mock.MagicMock) -> None:
    app, _, _ = create_app(database_url="")
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/check-model")
    assert resp.status_code == 200
    data = json.loads(resp.text)
    assert isinstance(data, dict)


def _make_status_app():
    """Helper to create app for status tests with mocking."""
    from src.backend.app import create_app

    with (
        mock.patch("src.backend.dependencies._get_dsn", return_value=None),
        mock.patch("src.model.llm_client.LLMClient.health_check", return_value=True),
        mock.patch("urllib.request.urlopen", side_effect=RuntimeError("no rag")),
    ):
        app, _, _ = create_app(database_url="")
    return app


def test_service_status_structure() -> None:
    app = _make_status_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "components" in data
    assert "app" in data["components"]
    assert "database" in data["components"]
    assert "llm" in data["components"]
    assert "rag" in data["components"]
    assert "timestamp" in data


def test_service_status_overall_ok() -> None:
    app = _make_status_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/status")
    data = resp.json()
    assert "status" in data


def test_service_status_degraded() -> None:
    app = _make_status_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/status")
    data = resp.json()
    assert data["components"]["rag"]["status"] == "error"
    assert data["status"] == "degraded"
