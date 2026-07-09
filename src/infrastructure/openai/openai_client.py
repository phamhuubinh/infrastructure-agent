from __future__ import annotations

import json
from urllib import error as urlerror
from urllib import request


class OpenAIClient:
    """
    Minimal HTTP client for an OpenAI-compatible chat completions API.

    If no model is explicitly provided, the client queries GET /v1/models
    once at construction time and uses the first available model.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str | None = None,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        if model is not None:
            self._model = model
        else:
            self._model = self._discover_model()

    @staticmethod
    def check_available(base_url: str = "http://localhost:8000", timeout: int = 3) -> bool:
        base_url = base_url.rstrip("/")
        try:
            req = request.Request(url=f"{base_url}/v1/models")
            with request.urlopen(req, timeout=timeout):
                return True
        except (OSError, urlerror.URLError):
            return False

    def _discover_model(self) -> str:
        try:
            req = request.Request(url=f"{self._base_url}/v1/models")
            headers: dict[str, str] = {}
            if self._api_key is not None:
                headers["Authorization"] = f"Bearer {self._api_key}"
            req.headers = headers
            with request.urlopen(req, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, urlerror.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Cannot reach OpenAI-compatible API at {self._base_url}/v1/models: {exc}"
            ) from exc

        data = body.get("data")
        if not isinstance(data, list) or len(data) == 0:
            raise RuntimeError(
                f"OpenAI-compatible API at {self._base_url} returned no models."
            )

        first = data[0]
        if not isinstance(first, dict):
            raise RuntimeError(f"Unexpected model list format from {self._base_url}.")
        model_id = first.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise RuntimeError(f"Unexpected model entry format from {self._base_url}.")

        return model_id

    def generate(
        self,
        prompt: str,
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }

        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = request.Request(
            url=f"{self._base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            raise RuntimeError(
                f"OpenAI API returned HTTP {exc.code} at {self._base_url}/v1/chat/completions "
                f"(model={self._model}). Verify the model name and endpoint."
            ) from exc

        return body["choices"][0]["message"]["content"]
