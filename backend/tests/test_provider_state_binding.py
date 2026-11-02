from __future__ import annotations

import asyncio

import pytest
from pydantic import SecretStr
from test_provider_registry import configured_settings, registered

from orion.contracts import (
    AssistantMessage,
    ModelTurn,
    ModelTurnCompleted,
    ProviderContinuation,
    RuntimeScope,
)
from orion.models.backend import ModelBackend, ModelBackendError
from orion.models.providers.continuation import ContinuationCodec
from orion.models.registry import ProviderRegistry


class PrivateBackend(ModelBackend):
    def __init__(self):
        self.states = []

    async def stream(self, messages, tools, settings, cancellation):
        self.states.append(settings.provider_continuation)
        yield ModelTurnCompleted(
            turn=ModelTurn(
                assistant=AssistantMessage(content="visible"),
                provider_continuation=ProviderContinuation(
                    adapter_id="claude.messages.v1", payload=SecretStr("private-native-state")
                ),
            )
        )


def scope(**changes):
    return RuntimeScope(
        **{"session_id": "session", "principal_id": "owner", "workspace_id": "workspace", **changes}
    )


@pytest.mark.anyio
async def test_registry_seals_state_but_returns_exact_native_payload_to_adapter():
    backend = PrivateBackend()
    registry = ProviderRegistry((registered(backend),))
    settings = configured_settings().model_copy(update={"runtime_scope": scope()})
    first = await registry.complete((), (), settings, asyncio.Event())
    assert first.provider_continuation.payload.get_secret_value() != "private-native-state"
    await registry.complete(
        (),
        (),
        settings.model_copy(update={"provider_continuation": first.provider_continuation}),
        asyncio.Event(),
    )
    assert backend.states[0] is None
    assert backend.states[1].payload.get_secret_value() == "private-native-state"
    assert "private-native-state" not in first.model_dump_json() + repr(first)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"request_binding": "different-request"},
        {"api_key": "rotated-key"},
        {"reasoning_mode": "enabled"},
        {"runtime_scope": scope(session_id="another-session")},
        {"runtime_scope": scope(project_id="another-project")},
        {"runtime_scope": scope(principal_id="another-owner")},
        {"runtime_scope": scope(workspace_id="another-workspace")},
        {"runtime_scope": scope(endpoint_id="a" * 32)},
    ],
)
async def test_state_cannot_cross_request_key_scope_or_profile_boundary(change):
    backend = PrivateBackend()
    registry = ProviderRegistry((registered(backend),))
    settings = configured_settings().model_copy(update={"runtime_scope": scope()})
    turn = await registry.complete((), (), settings, asyncio.Event())
    bound = settings.model_copy(
        update={"provider_continuation": turn.provider_continuation, **change}
    )
    with pytest.raises(ModelBackendError):
        await registry.complete((), (), bound, asyncio.Event())
    assert len(backend.states) == 1


def test_integrity_restart_and_profile_changes_reject_with_safe_error():
    settings = configured_settings()
    codec = ContinuationCodec("claude.messages.v1")
    state = codec.pack(settings, {"private": "private-native-state"})
    assert codec.unpack(settings, state) == {"private": "private-native-state"}
    tampered = state.model_copy(
        update={"payload": SecretStr(state.payload.get_secret_value() + " ")}
    )
    changed = settings.model_copy(
        update={"profile": settings.profile.model_copy(update={"profile_id": "other-profile"})}
    )
    for instance, bound, envelope in [
        (codec, settings, tampered),
        (ContinuationCodec(codec.adapter_id), settings, state),
        (codec, changed, state),
    ]:
        with pytest.raises(ModelBackendError) as caught:
            instance.unpack(bound, envelope)
        assert "private-native-state" not in str(caught.value)
