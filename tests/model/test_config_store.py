from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from src.model.config_store import ModelConfigStore


def test_empty_registry_is_valid(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    store.ensure_exists()
    assert store.list_public() == {"active_server": "", "models": []}
    assert store.active() is None


def test_upsert_redacts_secret_and_activates_model(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    result = store.upsert(
        "primary",
        {
            "provider": "openai",
            "base_url": "http://model:8000/",
            "model": "qwen",
            "api_key": "secret",
        },
    )

    assert result["active_server"] == ""
    assert result["models"][0]["api_key_configured"] is True
    assert "api_key" not in result["models"][0]
    assert store.get("primary")["api_key"] == "secret"
    assert store.get("primary")["base_url"] == "http://model:8000"
    assert "max_tokens" not in store.get("primary")


def test_upsert_accepts_openai_v1_url_and_stores_server_root(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        "primary", {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1"}
    )
    assert store.get("primary")["base_url"] == "https://api.openai.com"


def test_upsert_maps_loopback_to_docker_host_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORION_MODEL_HOST_ALIAS", "host.docker.internal")
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        "local",
        {
            "provider": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model": "qwen3:4b",
        },
    )

    assert store.get("local")["base_url"] == "http://host.docker.internal:11434"


def test_upsert_rejects_connection_name_that_cannot_be_used_in_api_path(
    tmp_path: Path,
) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    with pytest.raises(ValueError, match="letters, numbers"):
        store.upsert("team/model", {"base_url": "http://model", "model": "qwen"})


def test_upsert_rejects_invalid_base_url(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    with pytest.raises(ValueError, match="absolute"):
        store.upsert("primary", {"base_url": "model-host", "model": "qwen"})


def test_upsert_rejects_credentials_in_base_url(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    with pytest.raises(ValueError, match="must not contain credentials"):
        store.upsert(
            "primary", {"base_url": "https://user:pass@model", "model": "qwen"}
        )


def test_switch_and_delete_active_model(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert("one", {"base_url": "http://one", "model": "one"})
    store.upsert("two", {"base_url": "http://two", "model": "two"})

    with mock.patch("src.model.config_store.LLMClient.health_check", return_value=True):
        assert store.test("one")["health_state"] == "healthy"
        assert store.test("two")["health_state"] == "healthy"
    store.set_active("one")
    assert store.active()[0] == "one"
    assert store.delete("one") is True
    assert store.active()[0] == "two"
    assert store.delete("missing") is False


def test_health_state_survives_config_reload(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert("primary", {"base_url": "http://model", "model": "qwen"})

    assert store.list_public()["models"][0]["health_state"] == "configured_unknown"
    with mock.patch(
        "src.model.config_store.LLMClient.health_check", return_value=True
    ):
        assert store.test("primary")["health_state"] == "healthy"

    reloaded = ModelConfigStore(tmp_path / "models.json")
    model = reloaded.list_public()["models"][0]
    assert model["health_state"] == "healthy"
    assert model["available"] is True


def test_connection_test_uses_saved_model(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert("primary", {"base_url": "http://model", "model": "qwen"})
    with mock.patch(
        "src.model.config_store.LLMClient.health_check", return_value=True
    ) as health:
        assert store.test("primary", timeout=12)["status"] == "ok"
    health.assert_called_once_with(timeout=12)
