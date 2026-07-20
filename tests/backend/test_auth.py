from __future__ import annotations

import os
from unittest import mock

from src.backend.app import create_app


def test_health_endpoint_no_auth_required() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@mock.patch.dict(os.environ, {"ORION_API_KEY": "test-key-123"}, clear=False)
def test_api_key_required_when_configured() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200, "health should bypass auth"


@mock.patch.dict(os.environ, {"ORION_API_KEY": "test-key-123"}, clear=False)
def test_api_key_missing_returns_401() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/sessions")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or missing API key"


@mock.patch.dict(os.environ, {"ORION_API_KEY": "test-key-123"}, clear=False)
def test_api_key_wrong_returns_401() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/sessions", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


@mock.patch.dict(os.environ, {"ORION_API_KEY": "test-key-123"}, clear=False)
def test_api_key_bearer_token_valid() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/sessions", headers={"Authorization": "Bearer test-key-123"})
    assert resp.status_code == 200


@mock.patch.dict(os.environ, {"ORION_API_KEY": "test-key-123"}, clear=False)
def test_api_key_header_valid() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/sessions", headers={"X-API-Key": "test-key-123"})
    assert resp.status_code == 200


def test_no_auth_when_no_env_key() -> None:
    app, _, _ = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
