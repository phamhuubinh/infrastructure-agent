from __future__ import annotations

import asyncio

import httpx
import pytest
from conftest import ScriptedBackend

from orion.bootstrap import build_application
from orion.chat.deadline import RequestBudget, RequestBudgetSettings
from orion.chat.runtime import RequestFailed
from orion.contracts import ContextMessage
from orion.contracts.profiles import ModelCapabilities, ModelProfile
from orion.models.backend import ModelBackendError, ModelSettings
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.models.registry import AdapterRegistration, ProviderRegistry


def profile(**changes):
    return ModelProfile.model_validate(
        {
            "profile_id": "limited-profile",
            "provider_id": "openai_compatible",
            "protocol": "chat_completions",
            "endpoint": "http://fixture.test/v1",
            "model_id": "configured",
            "capabilities": ModelCapabilities(streaming=True),
            **changes,
        }
    )


def settings(value):
    return ModelSettings(
        provider_type=value.provider_id,
        base_url=value.endpoint,
        model_id=value.model_id,
        profile=value,
    )


def test_profile_deadline_shortens_both_work_and_finalization_without_extending_server_limit():
    original = RequestBudget.start(RequestBudgetSettings(), clock=lambda: 10.0)
    assert original.limited_to(200) is original
    limited = original.limited_to(1)
    assert limited.started_monotonic == 10
    assert limited.work_deadline_monotonic == 10.5
    assert limited.deadline_monotonic == 11
    assert original.deadline_monotonic == 130


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_profile_deadline_rejects_invalid_limits(seconds):
    with pytest.raises(ValueError):
        RequestBudget.start(RequestBudgetSettings()).limited_to(seconds)


@pytest.mark.anyio
async def test_actual_encoded_request_byte_bound_rejects_before_creating_http_client(monkeypatch):
    def unexpected_client(**kwargs):
        pytest.fail("Oversized wire request reached HTTP client")

    monkeypatch.setattr(
        "orion.models.providers.openai_compatible.httpx.AsyncClient", unexpected_client
    )
    value = profile(context_max_bytes=4096, request_max_bytes=4096)
    with pytest.raises(ModelBackendError, match="byte limit"):
        await OpenAICompatibleBackend().complete(
            (ContextMessage(role="user", content="秘" * 2000),),
            (),
            settings(value),
            asyncio.Event(),
        )


@pytest.mark.anyio
async def test_profile_transport_timeout_is_used_by_real_compatible_http_client(monkeypatch):
    captured = []
    client_type = httpx.AsyncClient

    def client(**kwargs):
        captured.append(kwargs["timeout"])
        return client_type(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    text=(
                        'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":"stop"}]}'
                        "\n\ndata: [DONE]\n\n"
                    ),
                )
            ),
            **kwargs,
        )

    monkeypatch.setattr("orion.models.providers.openai_compatible.httpx.AsyncClient", client)
    turn = await OpenAICompatibleBackend().complete(
        (), (), settings(profile(transport_timeout_seconds=7)), asyncio.Event()
    )
    assert turn.assistant.content == "Hello"
    assert captured == [7]


@pytest.mark.anyio
async def test_profile_context_limit_keeps_user_request_and_stops_before_model_dispatch(tmp_path):
    backend = ScriptedBackend([])
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
    application = build_application(tmp_path / "limited.db", registry)
    value = profile(context_max_bytes=4096, request_max_bytes=8192)
    content = "秘" * 2000
    try:
        application.store.create_model_config(
            value.provider_id, value.endpoint, value.model_id, None, profile=value
        )
        session = application.store.create_session()
        with pytest.raises(RequestFailed):
            await application.runtime.submit(session, content)
        assert not backend.calls
        assert (
            next(
                item.payload["content"]
                for item in application.store.timeline(session)
                if item.kind == "user_message"
            )
            == content
        )
    finally:
        application.store.close()


def test_bounded_retry_policy_is_accepted_without_dispatch():
    backend = ScriptedBackend([])
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
    _, bound = registry.resolve(settings(profile(safe_transport_retries=1)))
    assert bound.safe_transport_retries == 1
    assert not backend.calls


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["enabled", "disabled"])
async def test_unsupported_compatible_reasoning_override_rejects_before_transport(
    monkeypatch, mode
):
    monkeypatch.delenv("ORION_OPENAI_COMPAT_REASONING_TEMPLATE_KWARGS", raising=False)

    def unexpected_client(**kwargs):
        pytest.fail("Unsupported reasoning override reached HTTP transport")

    monkeypatch.setattr(
        "orion.models.providers.openai_compatible.httpx.AsyncClient", unexpected_client
    )
    bound = settings(profile()).model_copy(update={"reasoning_mode": mode})
    with pytest.raises(ModelBackendError, match="reasoning control support"):
        await OpenAICompatibleBackend().complete((), (), bound, asyncio.Event())
