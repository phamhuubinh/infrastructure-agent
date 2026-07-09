from __future__ import annotations

import pytest

from src.cli import _build_client


def test_openai_config_creates_openai_client() -> None:
    model = _build_client({
        "provider": "openai",
        "base_url": "http://test:8000",
        "model": "mymodel",
        "api_key": None,
    })
    assert type(model._client).__name__ == "OpenAIClient"
    assert model._client._base_url == "http://test:8000"
    assert model._client._model == "mymodel"


def test_ollama_config_creates_ollama_client() -> None:
    model = _build_client({
        "provider": "ollama",
        "base_url": "http://ollama:11434",
        "model": "mymodel",
    })
    assert type(model._client).__name__ == "OllamaClient"
    assert model._client._host == "http://ollama:11434"
    assert model._client._model == "mymodel"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        _build_client({
            "provider": "nonexistent",
            "base_url": "",
            "model": "x",
        })
