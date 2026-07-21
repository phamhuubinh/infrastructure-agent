from __future__ import annotations

import json
from urllib import error as urlerror
from urllib import request


class GrafanaProvider:
    def __init__(self, url: str, token: str, timeout: int = 10) -> None:
        self._url = url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def get(self, path: str) -> object:
        try:
            req = request.Request(
                url=f"{self._url}{path}", headers=self._headers, method="GET"
            )
            with request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, urlerror.URLError, json.JSONDecodeError) as exc:
            msg = f"Grafana API request failed: {exc}"
            raise RuntimeError(msg) from exc
