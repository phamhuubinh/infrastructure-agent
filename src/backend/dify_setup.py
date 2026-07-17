from __future__ import annotations

import json
import os
import time
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request

from src.backend.dify_client import DifyClient, wait_for_dify
from src.shared.logger import info as _info

_DIFY_API_URL: str = os.environ.get("DIFY_API_URL", "http://dify-api:5001")
_DIFY_WEB_URL: str = os.environ.get("DIFY_WEB_URL", "http://dify-web:3000")
_ADMIN_EMAIL = "admin@orion.local"
_ADMIN_PASSWORD = os.environ.get("DIFY_INIT_PASSWORD", "orion_dify")
_ADMIN_TOKEN: str | None = None


def _get_admin_token(client: DifyClient) -> str | None:
    global _ADMIN_TOKEN
    if _ADMIN_TOKEN:
        return _ADMIN_TOKEN

    payload = json.dumps(
        {
            "email": _ADMIN_EMAIL,
            "password": _ADMIN_PASSWORD,
            "language": "en-US",
        }
    ).encode("utf-8")

    try:
        req = request.Request(
            f"{_DIFY_API_URL}/api/login",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            _ADMIN_TOKEN = data.get("access_token") or data.get("token")
            if _ADMIN_TOKEN:
                _info("dify-setup", message="Admin token acquired")
            return _ADMIN_TOKEN
    except Exception as exc:
        _info("dify-setup", message=f"Login failed: {exc}")
        return None


def _admin_request(
    method: str,
    path: str,
    data: dict | None = None,
    token: str | None = None,
) -> dict:
    token = token or _ADMIN_TOKEN
    if not token:
        return {"error": "No admin token available"}

    url = f"{_DIFY_API_URL}/api{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        req = request.Request(url, data=body, headers=headers, method=method)
        with request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return {"error": f"HTTP {exc.code}: {detail}"}
    except (urlerror.URLError, OSError) as exc:
        return {"error": str(exc)[:300]}


def _create_app(
    client: DifyClient,
    name: str = "Orion Assistant",
    description: str = "Infrastructure investigation assistant",
) -> str | None:
    result = _admin_request(
        "POST",
        "/apps",
        data={
            "name": name,
            "description": description,
            "mode": "chat",
            "icon": "🤖",
            "icon_background": "#1E90FF",
        },
    )
    app_id = result.get("id") or result.get("app_id")
    if app_id:
        _info("dify-setup", message=f"App created", app_id=app_id)
    else:
        _info(
            "dify-setup",
            message="App creation returned no id",
            result=result.get("error", str(result)[:100]),
        )
    return app_id


def _get_or_create_app(client: DifyClient) -> str | None:
    result = _admin_request("GET", "/apps?page=1&limit=20")
    apps = result.get("data") or result.get("apps") or []
    if apps:
        app = apps[0]
        app_id = app.get("id")
        _info("dify-setup", message="Found existing app", app_id=app_id)
        return app_id
    return _create_app(client)


def _get_or_create_api_key(client: DifyClient, app_id: str) -> str | None:
    result = _admin_request("GET", f"/apps/{app_id}/api-keys")
    keys = (
        result.get("data") or result.get("keys") or []
        if isinstance(result, dict)
        else []
    )
    if keys:
        key = keys[0].get("token") or keys[0].get("api_key")
        if key:
            _info("dify-setup", message="Using existing API key")
            return key

    result = _admin_request("POST", f"/apps/{app_id}/api-keys")
    key = result.get("token") or result.get("api_key")
    if key:
        _info("dify-setup", message="API key created")
    return key


def _create_dataset(
    name: str = "Orion Knowledge Base",
    description: str = "Infrastructure documentation and runbooks",
) -> str | None:
    result = _admin_request(
        "POST",
        "/datasets",
        data={
            "name": name,
            "description": description,
            "indexing_technique": "economy",
            "permission": "only_me",
        },
    )
    dataset_id = result.get("id") or result.get("dataset_id")
    if dataset_id:
        _info("dify-setup", message="Dataset created", dataset_id=dataset_id)
    return dataset_id


def _get_or_create_dataset() -> str | None:
    result = _admin_request("GET", "/datasets?page=1&limit=20")
    datasets = result.get("data") or result.get("datasets") or []
    if datasets:
        ds = datasets[0]
        ds_id = ds.get("id")
        _info("dify-setup", message="Found existing dataset", dataset_id=ds_id)
        return ds_id
    return _create_dataset()


def setup_dify() -> bool:
    client = DifyClient(api_url=_DIFY_API_URL)

    if not wait_for_dify(client, max_retries=10):
        _info("dify-setup", message="Dify API not reachable, skipping setup")
        return False

    token = _get_admin_token(client)
    if not token:
        _info("dify-setup", message="No admin token, skipping setup")
        return False

    app_id = _get_or_create_app(client)
    if not app_id:
        _info("dify-setup", message="No app available, skipping setup")
        return False

    api_key = _get_or_create_api_key(client, app_id)
    if api_key:
        _info("dify-setup", message="Dify API key ready")

    dataset_id = _get_or_create_dataset()
    if dataset_id:
        _info("dify-setup", message="Dify dataset ready")

    _info(
        "dify-setup",
        message="Dify setup complete",
        app_id=app_id or "",
        dataset_id=dataset_id or "",
    )
    return True
