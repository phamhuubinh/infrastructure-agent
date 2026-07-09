from __future__ import annotations

import json
from urllib import request


class OpenAIClient:
    """
    Minimal HTTP client for an OpenAI-compatible chat completions API.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "default",
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

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

        with request.urlopen(req) as response:
            body = json.loads(response.read().decode("utf-8"))

        return body["choices"][0]["message"]["content"]
