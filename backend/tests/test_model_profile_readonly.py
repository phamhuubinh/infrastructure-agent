from __future__ import annotations

import sqlite3

import pytest

from orion.benchmarks import model_context as benchmark
from orion.bootstrap import build_application
from orion.contracts.profiles import ModelCapabilities, ModelProfile
from orion.persistence.sqlite import SQLiteStore


def test_readonly_binding_does_not_create_database_or_parent(tmp_path):
    path = tmp_path / "absent parent" / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        SQLiteStore.read_active_model_binding(path)
    assert not path.parent.exists()


def test_readonly_typed_binding_uses_shared_resolver_without_constructor_or_key_persistence(
    tmp_path, monkeypatch
):
    path = tmp_path / "state with spaces.db"
    profile = ModelProfile(
        profile_id="typed",
        provider_id="openai_compatible",
        protocol="chat_completions",
        endpoint="http://fixture.test/v1",
        model_id="configured",
        credential_ref="env:ORION_FIXTURE_KEY",
        capabilities=ModelCapabilities(streaming=True),
    )
    store = SQLiteStore(path)
    store.create_model_config(
        profile.provider_id, profile.endpoint, profile.model_id, None, profile=profile
    )
    store.close()
    before = path.read_bytes()
    monkeypatch.setenv("ORION_FIXTURE_KEY", "private-readonly-key")
    monkeypatch.setattr(benchmark, "database_path", lambda: path)

    def unexpected_init(*args, **kwargs):
        pytest.fail("Read-only profile resolution invoked schema creation/migration")

    monkeypatch.setattr(SQLiteStore, "__init__", unexpected_init)
    resolved = benchmark.active_model_settings()
    assert resolved.profile == profile
    assert resolved.api_key == "private-readonly-key"
    assert "private-readonly-key" not in resolved.model_dump_json()
    assert path.read_bytes() == before
    assert b"private-readonly-key" not in before


def test_legacy_readonly_binding_preserves_old_schema_and_credential(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE model_configs (model_config_id TEXT PRIMARY KEY, "
            "provider_type TEXT, base_url TEXT, model_id TEXT, api_key TEXT, "
            "reasoning_mode TEXT, is_active INTEGER, created_at TEXT)"
        )
        connection.execute(
            "INSERT INTO model_configs VALUES (?,?,?,?,?,?,?,?)",
            (
                "legacy",
                "openai_compatible",
                "http://fixture.test/v1",
                "configured",
                "retained-legacy-key",
                "auto",
                1,
                "now",
            ),
        )
    before = path.read_bytes()
    monkeypatch.setattr(benchmark, "database_path", lambda: path)
    settings = benchmark.active_model_settings()
    assert settings.api_key == "retained-legacy-key"
    assert settings.profile.provider_id == "openai_compatible"
    assert path.read_bytes() == before
    with sqlite3.connect(path) as connection:
        assert "profile_json" not in {
            row[1] for row in connection.execute("PRAGMA table_info(model_configs)")
        }


def test_isolated_bootstrap_can_disable_environment_model_secret_seeding(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_MODEL_BASE_URL", "http://fixture.test/v1")
    monkeypatch.setenv("ORION_MODEL_ID", "configured")
    monkeypatch.setenv("ORION_MODEL_API_KEY", "private-bootstrap-key")
    path = tmp_path / "isolated.db"
    application = build_application(path, seed_model_from_environment=False)
    try:
        assert application.store.model_configs() == []
    finally:
        application.store.close()
    assert b"private-bootstrap-key" not in path.read_bytes()
