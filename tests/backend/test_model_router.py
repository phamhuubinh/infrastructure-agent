from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi import HTTPException

from src.backend.routers import models
from src.model.config_store import ModelConfigStore


def _request(
    tmp_path: Path,
) -> tuple[SimpleNamespace, ModelConfigStore, mock.MagicMock]:
    store = ModelConfigStore(tmp_path / "servers.json")
    reload_models = mock.MagicMock()
    deps = SimpleNamespace(model_store=store, reload_models=reload_models)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(deps=deps)))
    return request, store, reload_models


def test_save_model_persists_secret_without_returning_it(tmp_path: Path) -> None:
    request, store, reload_models = _request(tmp_path)

    result = models.save_model(
        {
            "name": "primary",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4.1",
            "api_key": "secret",
        },
        request,
    )

    assert result["active_server"] == "primary"
    assert result["models"][0]["api_key_configured"] is True
    assert "api_key" not in result["models"][0]
    assert store.get("primary")["api_key"] == "secret"
    reload_models.assert_called_once_with()


def test_connection_test_returns_503_with_useful_error(tmp_path: Path) -> None:
    request, store, _reload_models = _request(tmp_path)
    store.upsert("primary", {"base_url": "http://model", "model": "qwen"})

    with (
        mock.patch.object(
            store,
            "test",
            return_value={
                "status": "error",
                "name": "primary",
                "error": "connection refused",
            },
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        models.test_model("primary", request, {"timeout": 12})

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "connection refused"


def test_delete_last_model_returns_to_setup_mode(tmp_path: Path) -> None:
    request, store, reload_models = _request(tmp_path)
    store.upsert("local", {"base_url": "http://ollama:11434", "model": "qwen3"})

    result = models.delete_model("local", request)

    assert result == {"active_server": "", "models": []}
    reload_models.assert_called_once_with()
