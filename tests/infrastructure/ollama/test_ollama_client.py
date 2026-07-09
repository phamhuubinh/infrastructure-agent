from __future__ import annotations

import json

from src.infrastructure.ollama.ollama_client import (
    OllamaClient,
)


class _MockResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_generate_returns_text(monkeypatch) -> None:
    def fake_urlopen(req, **kwargs):
        body = json.dumps({"response": "hello"}).encode("utf-8")
        return _MockResponse(body)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = OllamaClient()

    response = client.generate("Reply with exactly: hello")

    assert isinstance(response, str)
    assert response == "hello"
