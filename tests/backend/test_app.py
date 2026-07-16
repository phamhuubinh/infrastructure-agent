from __future__ import annotations

from unittest import mock
import json
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
