from __future__ import annotations

import json
from urllib import error as urlerror
from urllib import request


class _ZabbixAPI:
    def __init__(self, url: str, token: str, timeout: int = 10) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._request_id = 0

    def call(
        self,
        method: str,
        params: dict[str, object] | None = None,
        skip_auth: bool = False,
    ) -> object:
        self._request_id += 1
        payload: dict[str, object] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._request_id,
        }
        if not skip_auth:
            payload["auth"] = self._token

        body = json.dumps(payload).encode("utf-8")
        try:
            req = request.Request(
                url=f"{self._url}/api_jsonrpc.php",
                data=body,
                headers={"Content-Type": "application/json-rpc"},
                method="POST",
            )
            with request.urlopen(req, timeout=self._timeout) as response:
                data: dict[str, object] = json.loads(response.read().decode("utf-8"))
        except (OSError, urlerror.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Zabbix API request failed: {exc}") from exc

        error = data.get("error")
        if error is not None:
            msg = error.get("message", "unknown")
            detail = error.get("data", "")
            raise RuntimeError(f"Zabbix API error: {msg} - {detail}")

        result = data.get("result")
        if result is None:
            raise RuntimeError("Zabbix API returned no result.")
        return result
