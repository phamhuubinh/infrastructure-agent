from __future__ import annotations

import sqlite3

import httpx
import pytest
from conftest import ScriptedBackend

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.persistence.sqlite import SQLiteStore


def test_existing_single_model_database_migrates_without_losing_configuration(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """CREATE TABLE model_configs (
            model_config_id TEXT PRIMARY KEY,
            provider_type TEXT NOT NULL,
            base_url TEXT NOT NULL,
            model_id TEXT NOT NULL,
            api_key TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        "INSERT INTO model_configs VALUES (?, ?, ?, ?, ?, ?)",
        (
            "legacy-qwen",
            "openai_compatible",
            "http://localhost:8000/v1",
            "qwen3-32b",
            "secret",
            "now",
        ),
    )
    connection.commit()
    connection.close()

    store = SQLiteStore(database)

    assert store.active_model_config() == {
        "model_config_id": "legacy-qwen",
        "provider_type": "openai_compatible",
        "base_url": "http://localhost:8000/v1",
        "model_id": "qwen3-32b",
        "api_key": "secret",
        "reasoning_mode": "auto",
        "is_active": 1,
    }
    assert [config["model_config_id"] for config in store.model_configs()] == ["legacy-qwen"]


def test_saved_model_profiles_keep_one_active_and_preserve_omitted_api_keys(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteStore(tmp_path / "models.db")
    first = store.create_model_config(
        "openai_compatible", "http://first.test/v1", "qwen3-32b", "first-secret"
    )
    second = store.create_model_config(
        "openai_compatible",
        "http://second.test/v1",
        "qwen3-14b",
        "second-secret",
        "disabled",
    )

    assert [(item["model_config_id"], item["is_active"]) for item in store.model_configs()] == [
        (first, 1),
        (second, 0),
    ]
    assert store.update_model_config(
        first, "openai_compatible", "http://edited.test/v1", "qwen3-32b-edited", None
    )
    assert store.model_config(first)["api_key"] == "first-secret"  # type: ignore[index]
    assert store.model_config(first)["reasoning_mode"] == "auto"  # type: ignore[index]
    assert store.model_config(second)["reasoning_mode"] == "disabled"  # type: ignore[index]
    with pytest.raises(sqlite3.IntegrityError):
        store.create_model_config(
            "openai_compatible", "http://invalid.test/v1", "invalid", None, "sometimes"
        )
    assert store.activate_model_config(second)
    assert store.active_model_config()["model_config_id"] == second  # type: ignore[index]
    assert store.delete_model_config(second) == "active"
    assert store.delete_model_config(first) == "deleted"


def test_reasoning_mode_profiles_survive_update_activation_and_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "models.db"
    store = SQLiteStore(database)
    auto = store.create_model_config("openai_compatible", "http://auto.test/v1", "auto", None)
    enabled = store.create_model_config(
        "openai_compatible", "http://enabled.test/v1", "enabled", None, "enabled"
    )
    disabled = store.create_model_config(
        "openai_compatible", "http://disabled.test/v1", "disabled", None, "disabled"
    )

    assert store.update_model_config(
        enabled, "openai_compatible", "http://enabled-edited.test/v1", "enabled", None
    )
    assert store.activate_model_config(disabled)
    store.close()

    restarted = SQLiteStore(database)
    modes = {item["model_config_id"]: item["reasoning_mode"] for item in restarted.model_configs()}
    assert modes == {auto: "auto", enabled: "enabled", disabled: "disabled"}
    assert restarted.active_model_config()["model_config_id"] == disabled  # type: ignore[index]
    restarted.close()


def test_chat_runtime_resolves_the_currently_active_saved_profile(tmp_path) -> None:  # type: ignore[no-untyped-def]
    application = build_application(tmp_path / "runtime.db", ScriptedBackend([]))
    first = application.store.create_model_config(
        "openai_compatible", "http://first.test/v1", "qwen3-32b", None
    )
    second = application.store.create_model_config(
        "openai_compatible", "http://second.test/v1", "qwen3-14b", None, "enabled"
    )

    assert application.store.activate_model_config(second)
    settings = application.runtime._settings()  # noqa: SLF001 - verifies the sole runtime resolution.

    assert first != second
    assert settings.base_url == "http://second.test/v1"
    assert settings.model_id == "qwen3-14b"
    assert settings.reasoning_mode == "enabled"


@pytest.mark.anyio
async def test_model_profile_api_lists_switches_edits_and_deletes_without_exposing_keys(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path / "api.db", ScriptedBackend([]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/api/models",
            json={
                "provider_type": "openai_compatible",
                "base_url": "https://first-secret@first.test/v1?private=true",
                "model_id": "qwen3-32b",
                "api_key": "first-secret",
            },
        )
        second = await client.post(
            "/api/models",
            json={
                "provider_type": "openai_compatible",
                "base_url": "https://second.test/v1",
                "model_id": "qwen3-14b",
                "api_key": "second-secret",
                "reasoning_mode": "disabled",
            },
        )
        first_id = first.json()["model_config_id"]
        second_id = second.json()["model_config_id"]
        listed = await client.get("/api/models")
        edited = await client.put(
            f"/api/models/{first_id}",
            json={
                "provider_type": "openai_compatible",
                "base_url": "https://edited.test/v1",
                "model_id": "qwen3-32b-edited",
                "api_key": "",
                "reasoning_mode": "enabled",
            },
        )
        preserved = await client.put(
            f"/api/models/{second_id}",
            json={
                "provider_type": "openai_compatible",
                "base_url": "https://second-edited.test/v1",
                "model_id": "qwen3-14b-edited",
                "api_key": "",
            },
        )
        stored_key = app.state.application.store.model_config(first_id)["api_key"]  # type: ignore[index]
        activated = await client.post(f"/api/models/{second_id}/activate")
        deleted = await client.delete(f"/api/models/{first_id}")
        blocked = await client.delete(f"/api/models/{second_id}")

    assert first.status_code == 201
    assert first.json()["base_url"] == "https://first.test/v1"
    assert second.status_code == 201
    assert first.json()["reasoning_mode"] == "auto"
    assert second.json()["reasoning_mode"] == "disabled"
    assert [item["model_config_id"] for item in listed.json()] == [first_id, second_id]
    assert [item["is_active"] for item in listed.json()] == [True, False]
    assert "first-secret" not in str(listed.json())
    assert "second-secret" not in str(listed.json())
    assert "api_key" not in str(listed.json())
    assert edited.status_code == 200
    assert edited.json()["reasoning_mode"] == "enabled"
    assert preserved.status_code == 200
    assert preserved.json()["reasoning_mode"] == "disabled"
    assert stored_key == "first-secret"
    assert activated.status_code == 200 and activated.json()["is_active"] is True
    assert deleted.status_code == 204
    assert blocked.status_code == 409


@pytest.mark.anyio
async def test_model_profile_api_rejects_invalid_reasoning_mode(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path / "api.db", ScriptedBackend([]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/models",
            json={
                "provider_type": "openai_compatible",
                "base_url": "http://model.test/v1",
                "model_id": "fake",
                "reasoning_mode": "sometimes",
            },
        )

    assert response.status_code == 422
