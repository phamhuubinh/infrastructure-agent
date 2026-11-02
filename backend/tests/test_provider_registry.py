from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from conftest import ScriptedBackend

from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelTurn, ProviderContinuation
from orion.contracts.profiles import ModelCapabilities, ModelProfile
from orion.models.backend import ModelBackendError, ModelBackendErrorKind, ModelSettings
from orion.models.credentials import CredentialResolutionError, EnvironmentCredentialResolver
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.models.registry import AdapterRegistration, ProviderRegistry
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.calculator import calculator_definition


def configured_settings(**changes):
    profile = ModelProfile.model_validate(
        {
            "profile_id": "test-profile",
            "provider_id": "claude",
            "protocol": "anthropic_messages",
            "endpoint": "http://fixture.test/v1",
            "model_id": "owner-configured",
            "capabilities": ModelCapabilities(
                streaming=True, tools=True, tool_result_continuation=True
            ),
            **changes,
        }
    )
    return ModelSettings(
        provider_type=profile.provider_id,
        base_url=profile.endpoint,
        model_id=profile.model_id,
        profile=profile,
    )


def registered(backend, schema=None):
    return AdapterRegistration(
        adapter_id="claude.messages.v1",
        provider_id="claude",
        protocol="anthropic_messages",
        backend=backend,
        option_schema=schema or {"type": "object", "properties": {}, "additionalProperties": False},
    )


@pytest.mark.anyio
async def test_registry_routes_exact_profile_and_preserves_first_turn_tools():
    selected = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="selected"))])
    other = ScriptedBackend([])
    registry = ProviderRegistry(
        (
            registered(selected),
            AdapterRegistration(
                "openai.responses.v1",
                "openai",
                "openai_responses",
                other,
                {"type": "object", "additionalProperties": False},
            ),
        )
    )
    tools = (calculator_definition(),)
    turn = await registry.complete((), tools, configured_settings(), asyncio.Event())
    assert turn.assistant.content == "selected"
    assert selected.calls[0][1] == tools
    assert not other.calls


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"model_id": "another-model"},
        {"base_url": "http://another.test/v1"},
        {"provider_type": "openai"},
        {
            "provider_continuation": ProviderContinuation(
                adapter_id="other.adapter", payload="private"
            )
        },
    ],
)
async def test_registry_rejects_profile_or_adapter_mismatch_before_network(change):
    backend = ScriptedBackend([])
    registry = ProviderRegistry((registered(backend),))
    with pytest.raises(ModelBackendError) as caught:
        await registry.complete(
            (), (), configured_settings().model_copy(update=change), asyncio.Event()
        )
    assert caught.value.kind == ModelBackendErrorKind.UNSUPPORTED
    assert not backend.calls


@pytest.mark.anyio
async def test_no_native_adapter_fallback_and_no_model_name_inference():
    registry = ProviderRegistry(())
    with pytest.raises(ModelBackendError, match="no registered adapter"):
        await registry.complete((), (), configured_settings(), asyncio.Event())
    settings = configured_settings().model_copy(update={"profile": None})
    with pytest.raises(ModelBackendError, match="explicit provider profile"):
        await registry.complete((), (), settings, asyncio.Event())


@pytest.mark.anyio
async def test_direct_legacy_adapter_cannot_misroute_a_native_profile(monkeypatch):
    def unexpected_client(**kwargs):
        pytest.fail("Native profile reached compatible HTTP transport")

    monkeypatch.setattr(
        "orion.models.providers.openai_compatible.httpx.AsyncClient", unexpected_client
    )
    with pytest.raises(ModelBackendError, match="explicitly compatible"):
        await OpenAICompatibleBackend().complete((), (), configured_settings(), asyncio.Event())


@pytest.mark.anyio
async def test_capability_and_options_checks_precede_dispatch():
    backend = ScriptedBackend([])
    registry = ProviderRegistry((registered(backend),))
    for changes, tools in [
        ({"options": {"unsupported": True}}, ()),
        ({"capabilities": ModelCapabilities()}, ()),
        ({"capabilities": ModelCapabilities(streaming=True)}, (calculator_definition(),)),
    ]:
        with pytest.raises(ModelBackendError) as caught:
            await registry.complete((), tools, configured_settings(**changes), asyncio.Event())
        assert caught.value.kind == ModelBackendErrorKind.UNSUPPORTED
    with pytest.raises(ModelBackendError, match="reasoning controls"):
        await registry.complete(
            (),
            (),
            configured_settings().model_copy(update={"reasoning_mode": "enabled"}),
            asyncio.Event(),
        )
    assert not backend.calls


def test_registry_snapshots_schemas_and_rejects_duplicate_registration():
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    backend = ScriptedBackend([])
    registration = registered(backend, schema)
    registry = ProviderRegistry((registration,))
    schema["additionalProperties"] = True
    with pytest.raises(ModelBackendError, match="options"):
        registry.resolve(configured_settings(options={"injected": 1}))
    with pytest.raises(ValueError, match="duplicate"):
        ProviderRegistry((registration, registration))


def test_explicit_credential_reference_is_resolved_once_and_not_serialized(monkeypatch):
    monkeypatch.setenv("ORION_FIXTURE_KEY", "first-private-key")
    resolver = EnvironmentCredentialResolver()
    registry = ProviderRegistry((registered(ScriptedBackend([])),))
    profile = configured_settings(credential_ref="env:ORION_FIXTURE_KEY").profile
    bound = registry.bind_profile(profile, resolver)
    monkeypatch.setenv("ORION_FIXTURE_KEY", "changed-private-key")
    assert bound.api_key == "first-private-key"
    assert "first-private-key" not in bound.model_dump_json()
    assert "first-private-key" not in repr(bound)
    assert bound.profile == profile


@pytest.mark.parametrize(
    "reference,value",
    [
        ("inline:private-key", "unused"),
        ("env:ORION_FIXTURE_KEY", None),
        ("env:ORION_FIXTURE_KEY", "private\r\nheader"),
        ("env:ORION_FIXTURE_KEY", "x" * 16_385),
    ],
)
def test_credential_failures_do_not_echo_secret_or_reference(monkeypatch, reference, value):
    if value is None:
        monkeypatch.delenv("ORION_FIXTURE_KEY", raising=False)
    else:
        monkeypatch.setenv("ORION_FIXTURE_KEY", value)
    with pytest.raises(CredentialResolutionError) as caught:
        EnvironmentCredentialResolver().resolve(reference)
    assert reference not in str(caught.value)
    assert value is None or value not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize("typed", [False, True])
async def test_default_application_uses_registry_for_real_compatible_tool_roundtrip(
    tmp_path, monkeypatch, typed
):
    calls = []

    def provider(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload["model"] == "configured-model"
        if typed:
            assert request.headers["Authorization"] == "Bearer first-private-key"
        if len(calls) == 1:
            replacement = application.store.create_model_config(
                "openai_compatible", "http://fixture.test/v1", "next-request-model", None
            )
            application.store.activate_model_config(replacement)
            monkeypatch.setenv("ORION_FIXTURE_KEY", "changed-private-key")
            assert any(t["function"]["name"] == "calculator.evaluate" for t in payload["tools"])
            delta = {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "calc-a",
                        "function": {
                            "name": "calculator.evaluate",
                            "arguments": '{"expression":"2+3"}',
                        },
                    }
                ]
            }
        else:
            assert any(
                m["role"] == "tool" and m["tool_call_id"] == "calc-a" for m in payload["messages"]
            )
            delta = {"content": "5"}
        body = (
            "data: "
            + json.dumps({"choices": [{"delta": delta, "finish_reason": "stop"}]})
            + "\n\ndata: [DONE]\n\n"
        )
        return httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        "orion.models.providers.openai_compatible.httpx.AsyncClient",
        lambda **kw: client_type(transport=httpx.MockTransport(provider), **kw),
    )
    application = build_application(tmp_path / "application.db")
    try:
        assert isinstance(application.backend, ProviderRegistry)
        profile = None
        if typed:
            monkeypatch.setenv("ORION_FIXTURE_KEY", "first-private-key")
            profile = ModelProfile(
                profile_id="typed-profile",
                provider_id="openai_compatible",
                protocol="chat_completions",
                endpoint="http://fixture.test/v1",
                model_id="configured-model",
                credential_ref="env:ORION_FIXTURE_KEY",
                capabilities=ModelCapabilities(
                    streaming=True, tools=True, tool_result_continuation=True
                ),
            )
        application.store.create_model_config(
            "openai_compatible", "http://fixture.test/v1", "configured-model", None, profile=profile
        )
        outcome = await application.runtime.submit(
            application.store.create_session(), "Calculate 2+3"
        )
        assert outcome.assistant_content == "5"
        assert len(calls) == 2
        assert application.runtime._settings().model_id == "next-request-model"
    finally:
        application.store.close()


def test_typed_profile_survives_restart_without_persisting_resolved_key(tmp_path):
    path = tmp_path / "typed.db"
    profile = configured_settings(credential_ref="env:ORION_FIXTURE_KEY").profile
    store = SQLiteStore(path)
    identity = store.create_model_config(
        profile.provider_id, profile.endpoint, profile.model_id, None, profile=profile
    )
    assert identity == profile.profile_id
    assert store.model_config(identity)["api_key"] is None
    assert not store.update_model_config(
        identity, "openai_compatible", "http://other.test", "other", "injected-key"
    )
    store.close()
    reopened = SQLiteStore(path)
    try:
        assert reopened.model_profile(identity) == profile
        config, saved = reopened.active_model_binding()
        assert saved == profile and config["api_key"] is None
        assert b"injected-key" not in path.read_bytes()
    finally:
        reopened.close()
