from __future__ import annotations

import json
import os
import socket
import urllib.request
from pathlib import Path

import pytest


def _load_api_key() -> str | None:
    value = os.environ.get("ORION_API_KEY", "").strip()
    if value:
        return value
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return None
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ORION_API_KEY="):
                return line.split("=", 1)[1].strip() or None
    except OSError:
        return None
    return None


API_URL = os.environ.get("API_URL", "http://localhost:61888")
API_KEY = _load_api_key()


def _request(url: str) -> urllib.request.Request:
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    return urllib.request.Request(url, headers=headers)


def _server_reachable(url: str) -> bool:
    try:
        host = url.split("://")[1].split(":")[0].split("/")[0]
        port = int(url.split(":")[-1].split("/")[0])
    except (IndexError, ValueError):
        return False
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _server_reachable(API_URL),
    reason="Docker containers not running — smoke tests require `docker compose up`",
)


def test_api_health_endpoint() -> None:
    resp = urllib.request.urlopen(_request(f"{API_URL}/api/health"), timeout=10)
    assert resp.status == 200
    data = json.loads(resp.read().decode())
    assert data["status"] == "ok"


def test_api_rag_health() -> None:
    resp = urllib.request.urlopen(_request(f"{API_URL}/api/rag/health"), timeout=10)
    assert resp.status == 200
    data = json.loads(resp.read().decode())
    assert "status" in data


def test_ui_is_serving() -> None:
    ui_url = os.environ.get("UI_URL", "http://localhost:80")
    resp = urllib.request.urlopen(ui_url, timeout=10)
    assert resp.status == 200
    body = resp.read().decode("utf-8", errors="replace")
    assert len(body) > 0


def test_reverse_proxy_routes_to_api() -> None:
    proxy_url = os.environ.get("PROXY_URL", "http://localhost:80")
    resp = urllib.request.urlopen(_request(f"{proxy_url}/api/health"), timeout=10)
    assert resp.status == 200
    data = json.loads(resp.read().decode())
    assert data["status"] == "ok"
