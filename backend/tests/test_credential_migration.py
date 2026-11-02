from __future__ import annotations

import sqlite3

import httpx
import pytest
from conftest import ScriptedBackend

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.models.backend import ModelBackendError
from orion.models.credential_store import credentials_for_database
from orion.models.credentials import CredentialResolutionError


def legacy_application(tmp_path):
    path = tmp_path / "application.db"
    app = build_application(path, ScriptedBackend([]), seed_model_from_environment=False)
    identity = app.store.create_model_config(
        "openai_compatible", "http://fixture.test/v1", "configured", "legacy-private-key"
    )
    return path, app, identity


def test_legacy_migration_verifies_copy_and_preserves_history_and_configuration(tmp_path):
    path, app, identity = legacy_application(tmp_path)
    session = app.store.create_session()
    app.store.append_timeline(session, None, "user_message", {"content": "Preserve this history"})
    before = app.store.timeline(session)
    configuration = app.store.model_config(identity)
    try:
        result = app.model_configurations.migrate_legacy_credentials()
        assert (result.migrated, result.changed_during_migration, result.remaining) == (1, 0, 0)
        stored, profile = app.store.active_model_binding()
        assert profile is None and stored["api_key"] is None
        assert stored["credential_ref"].startswith("secret:")
        assert (
            credentials_for_database(path).resolve(stored["credential_ref"]).get_secret_value()
            == "legacy-private-key"
        )
        assert app.runtime._settings().api_key == "legacy-private-key"
        assert app.store.timeline(session) == before
        assert app.store.model_config(identity) == {**configuration, "api_key": None}
        repeated = app.model_configurations.migrate_legacy_credentials()
        assert repeated.migrated == repeated.remaining == 0
        assert len(credentials_for_database(path).store.references()) == 1
        with pytest.raises(ModelBackendError, match="still referenced"):
            app.model_configurations.delete_credential(stored["credential_ref"])
    finally:
        app.store.close()


def test_failed_protected_copy_leaves_original_credential_untouched(tmp_path, monkeypatch):
    path, app, identity = legacy_application(tmp_path)

    def failed(*args, **kwargs):
        raise CredentialResolutionError("storage unavailable")

    monkeypatch.setattr("orion.models.credential_store.ProtectedFileCredentialStore.put", failed)
    try:
        with pytest.raises(ModelBackendError, match="storage failed"):
            app.model_configurations.migrate_legacy_credentials()
        assert app.store.model_config(identity)["api_key"] == "legacy-private-key"
        assert credentials_for_database(path).store.references() == ()
    finally:
        app.store.close()


def test_concurrent_rotation_is_not_overwritten_and_protected_recovery_copy_survives(
    tmp_path, monkeypatch
):
    path, app, identity = legacy_application(tmp_path)
    original = app.store.migrate_model_credential

    def rotate(config_id, expected, reference):
        app.store.update_model_config(
            config_id,
            "openai_compatible",
            "http://fixture.test/v1",
            "configured",
            "concurrent-private-key",
        )
        return original(config_id, expected, reference)

    monkeypatch.setattr(app.store, "migrate_model_credential", rotate)
    try:
        result = app.model_configurations.migrate_legacy_credentials()
        assert (result.migrated, result.changed_during_migration, result.remaining) == (0, 1, 1)
        assert app.store.model_config(identity)["api_key"] == "concurrent-private-key"
        store = credentials_for_database(path).store
        assert len(store.references()) == 1
        assert store.resolve(store.references()[0]).get_secret_value() == "legacy-private-key"
    finally:
        app.store.close()


def test_uncertain_database_failure_retains_original_and_protected_copy(tmp_path, monkeypatch):
    path, app, identity = legacy_application(tmp_path)

    def failed(*args, **kwargs):
        raise sqlite3.OperationalError("fixture persistence failure")

    monkeypatch.setattr(app.store, "migrate_model_credential", failed)
    try:
        with pytest.raises(ModelBackendError, match="protected copies were retained"):
            app.model_configurations.migrate_legacy_credentials()
        assert app.store.model_config(identity)["api_key"] == "legacy-private-key"
        store = credentials_for_database(path).store
        assert store.resolve(store.references()[0]).get_secret_value() == "legacy-private-key"
    finally:
        app.store.close()


@pytest.mark.anyio
async def test_new_http_key_is_never_written_to_database_and_empty_edit_preserves_binding(tmp_path):
    path = tmp_path / "api.db"
    app = create_app(path, ScriptedBackend([]))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            config = {
                "provider_type": "openai_compatible",
                "base_url": "http://fixture.test/v1",
                "model_id": "configured",
                "api_key": "new-private-api-key",
            }
            created = await client.post("/api/models", json=config)
            assert created.status_code == 201
            identity = created.json()["model_config_id"]
            before = app.state.application.store.active_model_binding()[0]["credential_ref"]
            assert "new-private-api-key" not in created.text
            edited = await client.put(
                f"/api/models/{identity}", json={**config, "api_key": "", "model_id": "updated"}
            )
            assert edited.status_code == 200
            stored = app.state.application.store.active_model_binding()[0]
            assert stored["api_key"] is None and stored["credential_ref"] == before
            assert app.state.application.runtime._settings().api_key == "new-private-api-key"
    finally:
        app.state.application.store.close()
    assert b"new-private-api-key" not in path.read_bytes()


@pytest.mark.anyio
async def test_core_without_injected_resolver_cannot_silently_drop_a_credential_reference(tmp_path):
    from conftest import runtime

    from orion.chat.runtime import RequestFailed
    from orion.persistence.sqlite import SQLiteStore

    store = SQLiteStore(tmp_path / "direct.db")
    backend = ScriptedBackend([])
    try:
        store.create_model_config(
            "openai_compatible",
            "http://fixture.test/v1",
            "configured",
            None,
            credential_ref="env:ORION_FIXTURE_KEY",
        )
        with pytest.raises(RequestFailed, match="application settings resolver"):
            await runtime(store, backend).submit(store.create_session(), "Hello")
        assert not backend.calls
    finally:
        store.close()
