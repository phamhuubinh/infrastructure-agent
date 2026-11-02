from __future__ import annotations

import httpx
import pytest
from conftest import ScriptedBackend

from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelTurn
from orion.contracts.profiles import ModelCapabilities, ModelProfile
from orion.models.registry import AdapterRegistration, ProviderRegistry


def profile(**changes):
    return ModelProfile.model_validate(
        {
            "profile_id": "profile-a",
            "provider_id": "openai_compatible",
            "protocol": "chat_completions",
            "endpoint": "http://fixture.test/v1",
            "model_id": "configured-model",
            "credential_ref": "env:ORION_FIXTURE_KEY",
            "capabilities": ModelCapabilities(
                streaming=True, tools=True, tool_result_continuation=True, reasoning_controls=True
            ),
            **changes,
        }
    )


def body(value, **changes):
    return {
        "provider_type": value.provider_id,
        "base_url": value.endpoint,
        "model_id": value.model_id,
        "profile": value.model_dump(mode="json"),
        **changes,
    }


@pytest.mark.anyio
async def test_typed_profile_http_lifecycle_and_missing_credential_preserve_active_selection(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ORION_FIXTURE_KEY", "private-provider-key")
    monkeypatch.setenv("ORION_OPENAI_COMPAT_REASONING_TEMPLATE_KWARGS", "1")
    app = create_app(tmp_path / "profiles.db")
    store = app.state.application.store
    value = profile()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post("/api/models", json=body(value))
            assert created.status_code == 201, created.text
            assert created.json()["profile"]["credential_ref"] == "env:ORION_FIXTURE_KEY"
            assert store.model_config(value.profile_id)["api_key"] is None
            assert "private-provider-key" not in created.text
            assert (await client.post("/api/models", json=body(value))).status_code == 409
            replacement = value.model_copy(update={"model_id": "updated-model"})
            edited = await client.put(
                "/api/models/profile-a", json=body(replacement, reasoning_mode="enabled")
            )
            assert edited.status_code == 200, edited.text
            settings = app.state.application.runtime._settings()
            assert settings.model_id == "updated-model" and settings.reasoning_mode == "enabled"
            assert settings.api_key == "private-provider-key"
            partial = await client.put(
                "/api/models/profile-a",
                json={
                    "provider_type": "openai_compatible",
                    "base_url": value.endpoint,
                    "model_id": "partial",
                    "api_key": "inline-key",
                },
            )
            assert partial.status_code == 409
            assert store.model_profile("profile-a").model_id == "updated-model"
            legacy = await client.post(
                "/api/models",
                json={
                    "provider_type": "openai_compatible",
                    "base_url": value.endpoint,
                    "model_id": "legacy",
                },
            )
            identity = legacy.json()["model_config_id"]
            assert (await client.post(f"/api/models/{identity}/activate")).status_code == 200
            monkeypatch.delenv("ORION_FIXTURE_KEY")
            unavailable = await client.post("/api/models/profile-a/activate")
            assert unavailable.status_code == 400
            assert store.active_model_config()["model_config_id"] == identity
            monkeypatch.setenv("ORION_FIXTURE_KEY", "rotated-private-key")
            assert (await client.post("/api/models/profile-a/activate")).status_code == 200
            assert (await client.delete("/api/models/profile-a")).status_code == 409
            await client.post(f"/api/models/{identity}/activate")
            assert (await client.delete("/api/models/profile-a")).status_code == 204
    finally:
        store.close()


@pytest.mark.anyio
async def test_profile_validation_never_echoes_request_key_and_unsupported_native_does_not_persist(
    tmp_path,
):
    application = build_application(
        tmp_path / "validation.db", ProviderRegistry(()), seed_model_from_environment=False
    )
    app = create_app(application=application)
    store = app.state.application.store
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            invalid = await client.post(
                "/api/models",
                json={
                    "provider_type": "claude",
                    "base_url": "http://fixture.test",
                    "model_id": "configured",
                    "api_key": "private-validation-key",
                },
            )
            assert invalid.status_code == 422
            assert "private-validation-key" not in invalid.text
            assert all(
                "input" not in item and "ctx" not in item for item in invalid.json()["detail"]
            )
            invalid_port = await client.post(
                "/api/models",
                json={
                    "provider_type": "openai_compatible",
                    "base_url": "http://fixture.test:private-validation-key",
                    "model_id": "configured",
                    "api_key": "private-validation-key",
                },
            )
            assert invalid_port.status_code == 422
            assert "private-validation-key" not in invalid_port.text
            native = profile(
                provider_id="claude", protocol="anthropic_messages", credential_ref=None
            )
            unavailable = await client.post("/api/models", json=body(native))
            assert unavailable.status_code == 400
            assert store.model_configs() == []
    finally:
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "vendor,protocol",
    [
        ("deepseek", "chat_completions"),
        ("claude", "anthropic_messages"),
        ("openai", "openai_responses"),
    ],
)
async def test_production_native_profile_without_credential_reference_cannot_replace_active(
    tmp_path, vendor, protocol
):
    app = create_app(tmp_path / "native-auth.db")
    store = app.state.application.store
    existing = store.create_model_config(
        "openai_compatible", "http://fixture.test/v1", "existing-local", None
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            missing = profile(provider_id=vendor, protocol=protocol, credential_ref=None)
            response = await client.post("/api/models", json=body(missing))
            assert response.status_code == 400
            assert store.active_model_config()["model_config_id"] == existing
            assert store.model_profile(missing.profile_id) is None
    finally:
        store.close()


@pytest.mark.anyio
async def test_three_native_profile_ids_route_through_same_api_and_runtime_with_fake_adapters(
    tmp_path,
):
    pairs = [
        ("deepseek", "chat_completions"),
        ("claude", "anthropic_messages"),
        ("openai", "openai_responses"),
    ]
    registrations = tuple(
        AdapterRegistration(
            f"{vendor}.fixture",
            vendor,
            protocol,
            ScriptedBackend([ModelTurn(assistant=AssistantMessage(content=vendor))]),
            {"type": "object", "properties": {}, "additionalProperties": False},
        )
        for vendor, protocol in pairs
    )
    application = build_application(tmp_path / "three.db", ProviderRegistry(registrations))
    app = create_app(application=application)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for vendor, protocol in pairs:
                value = profile(
                    profile_id=f"{vendor}-profile",
                    provider_id=vendor,
                    protocol=protocol,
                    credential_ref=None,
                )
                saved = await client.post("/api/models", json=body(value))
                assert saved.status_code == 201, saved.text
                assert (
                    await client.post(f"/api/models/{value.profile_id}/activate")
                ).status_code == 200
                outcome = await application.runtime.submit(
                    application.store.create_session(), "Hello"
                )
                assert outcome.assistant_content == vendor
    finally:
        application.store.close()


@pytest.mark.anyio
async def test_text_only_profile_keeps_single_runtime_without_unsupported_tool_schemas(tmp_path):
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Hello"))])
    registry = ProviderRegistry(
        (
            AdapterRegistration(
                "compatible.fixture",
                "openai_compatible",
                "chat_completions",
                backend,
                {"type": "object", "additionalProperties": False},
            ),
        )
    )
    application = build_application(tmp_path / "text.db", registry)
    value = profile(credential_ref=None, capabilities=ModelCapabilities(streaming=True))
    try:
        application.store.create_model_config(
            value.provider_id, value.endpoint, value.model_id, None, profile=value
        )
        outcome = await application.runtime.submit(application.store.create_session(), "Hello")
        assert outcome.assistant_content == "Hello"
        assert backend.calls[0][1] == ()
    finally:
        application.store.close()
