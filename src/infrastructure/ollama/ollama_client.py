from __future__ import annotations

import json
from urllib import error as urlerror
from urllib import request


class OllamaClient:
    """
    Minimal HTTP client for the Ollama API.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen3:14b",
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model

    @staticmethod
    def check_available(host: str = "http://localhost:11434", timeout: int = 3) -> bool:
        host = host.rstrip("/")
        try:
            req = request.Request(url=f"{host}/api/tags")
            with request.urlopen(req, timeout=timeout) as response:
                return True
        except (OSError, urlerror.URLError):
            return False

    def generate(
        self,
        prompt: str,
    ) -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }

        req = request.Request(
            url=f"{self._host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with request.urlopen(req) as response:
            body = json.loads(response.read().decode("utf-8"))

        return body["response"]
