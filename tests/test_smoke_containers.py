from __future__ import annotations

import json
import os
import urllib.request

API_URL = os.environ.get("API_URL", "http://localhost:61888")


def test_api_health_endpoint() -> None:
    resp = urllib.request.urlopen(f"{API_URL}/api/health", timeout=10)
    assert resp.status == 200
    data = json.loads(resp.read().decode())
    assert data["status"] == "ok"


def test_api_knowledge_health() -> None:
    resp = urllib.request.urlopen(f"{API_URL}/api/knowledge/health", timeout=10)
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
    resp = urllib.request.urlopen(f"{proxy_url}/api/health", timeout=10)
    assert resp.status == 200
    data = json.loads(resp.read().decode())
    assert data["status"] == "ok"
