from __future__ import annotations

import json
import os
import time
from urllib import error as urlerror
from urllib import request

_DIFY_API_URL: str = os.environ.get("DIFY_API_URL", "http://dify-api:5001")
_DEFAULT_TIMEOUT = 30
_RETRY_DELAY = 2
_MAX_RETRIES = 5


class DifyClient:
    def __init__(self, api_url: str = "", api_key: str = "") -> None:
        self._api_url = (api_url or _DIFY_API_URL).rstrip("/")
        self._api_key = api_key

    @property
    def api_url(self) -> str:
        return self._api_url

    def health(self) -> dict:
        try:
            resp = request.urlopen(f"{self._api_url}/health", timeout=5)
            return {"status": "ok", "code": resp.status}
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:200]}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> dict:
        url = f"{self._api_url}/v1{path}"
        body = json.dumps(data).encode("utf-8") if data else None
        req = request.Request(
            url,
            data=body,
            headers=self._headers(),
            method=method,
        )
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _request_raw(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> dict:
        url = f"{self._api_url}/v1{path}"
        body = json.dumps(data).encode("utf-8") if data else None
        req = request.Request(
            url,
            data=body,
            headers=self._headers(),
            method=method,
        )
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            return {"error": f"HTTP {exc.code}: {detail}"}
        except (urlerror.URLError, OSError) as exc:
            return {"error": str(exc)[:200]}

    def chat(
        self,
        query: str,
        user: str = "orion-user",
        conversation_id: str = "",
        response_mode: str = "blocking",
    ) -> dict:
        payload = {
            "inputs": {},
            "query": query,
            "response_mode": response_mode,
            "conversation_id": conversation_id,
            "user": user,
        }
        return self._request_raw("POST", "/chat-messages", data=payload)

    def knowledge_query(
        self,
        query: str,
        dataset_id: str,
        top_k: int = 5,
    ) -> dict:
        payload = {
            "query": query,
            "dataset_id": dataset_id,
            "top_k": top_k,
        }
        return self._request_raw("POST", "/datasets/documents/retrieve", data=payload)


def wait_for_dify(client: DifyClient, max_retries: int = _MAX_RETRIES) -> bool:
    for _attempt in range(1, max_retries + 1):
        health = client.health()
        if health.get("status") == "ok":
            return True
        time.sleep(_RETRY_DELAY)
    return False
