"""Private protocol state follows the existing tool loop, never public history."""

from __future__ import annotations

import json

import pytest
from conftest import runtime
from pydantic import ValidationError

from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ProviderContinuation,
)
from orion.models.backend import ModelBackend, ModelSettings


def test_private_envelope_excludes_payload_from_serialization_and_repr():
    state = ProviderContinuation(adapter_id="fixture.v1", payload="private-protocol-token")
    turn = ModelTurn(assistant=AssistantMessage(content="Visible."), provider_continuation=state)
    settings = ModelSettings(
        provider_type="openai_compatible",
        base_url="http://fixture.test",
        model_id="fixture",
        api_key="private-api-key",
        provider_continuation=state,
    )
    for value in (state, turn, ModelTurnCompleted(turn=turn), settings):
        assert "private-protocol-token" not in value.model_dump_json()
        assert "private-protocol-token" not in repr(value)
    assert state.payload.get_secret_value() == "private-protocol-token"
    assert "provider_continuation" not in turn.model_dump()
    assert "provider_continuation" not in settings.model_dump()
    assert "api_key" not in settings.model_dump()
    assert "private-api-key" not in repr(settings)
    assert settings.api_key == "private-api-key"


def test_invalid_settings_do_not_include_credential_in_validation_error():
    with pytest.raises(ValidationError) as caught:
        ModelSettings.model_validate({"api_key": "private-api-key"})
    assert "private-api-key" not in str(caught.value)


@pytest.mark.parametrize("payload", ["", "秘密" * 100_000])
def test_continuation_bounds_use_utf8_bytes_and_errors_hide_input(payload):
    with pytest.raises(ValidationError) as caught:
        ProviderContinuation(adapter_id="fixture.v1", payload=payload)
    assert "秘密" not in str(caught.value)


@pytest.mark.anyio
async def test_private_state_survives_two_tool_roundtrips_but_not_next_request(store):
    tokens = ["private-first-token", "private-second-token", "private-final-token"]
    seen = []

    class StatefulBackend(ModelBackend):
        async def stream(self, messages, tools, settings, cancellation):
            seen.append(settings.provider_continuation)
            assert not any(token in str(messages) for token in tokens)
            index = len(seen) - 1
            state = (
                ProviderContinuation(adapter_id="fixture.v1", payload=tokens[index])
                if index < 3
                else None
            )
            if index < 2:
                turn = ModelTurn(
                    tool_calls=(
                        ModelToolCall(
                            call_id=f"calc-{index}",
                            tool_name="calculator.evaluate",
                            arguments={"expression": "2+3"},
                        ),
                    ),
                    provider_continuation=state,
                )
            else:
                turn = ModelTurn(
                    assistant=AssistantMessage(content="Done."), provider_continuation=state
                )
            yield ModelTurnCompleted(turn=turn)

    sink = BoundedModelInputDiagnostics()
    chat = runtime(store, StatefulBackend())
    chat._diagnostic_sink = sink
    session = store.create_session()
    first = await chat.submit(session, "Calculate twice")
    second = await chat.submit(session, "Hello")
    assert [item.payload.get_secret_value() if item else None for item in seen] == [
        None,
        tokens[0],
        tokens[1],
        None,
    ]
    assert first.assistant_content == second.assistant_content == "Done."
    public = json.dumps(
        {
            "timeline": [item.model_dump(mode="json") for item in store.timeline(session)],
            "events": store.events(first.request_id) + store.events(second.request_id),
            "diagnostics": [sink.records(first.request_id), sink.records(second.request_id)],
        }
    )
    assert not any(token in public for token in tokens)
    assert sum(item.kind == "tool_result" for item in store.timeline(session)) == 2
