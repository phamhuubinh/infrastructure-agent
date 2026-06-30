from __future__ import annotations

from src.infrastructure.ollama.ollama_client import (
    OllamaClient,
)


def test_generate_returns_text() -> None:
    client = OllamaClient()

    response = client.generate("Reply with exactly: hello")

    assert isinstance(response, str)
    assert len(response) > 0
