from __future__ import annotations

import pytest
from conftest import ScriptedBackend, runtime

from orion.chat.runtime import _recoverable_failure_fingerprint
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn, ToolCall, ToolDefinition, ToolResult
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistryBuilder

_TOOL_NAME = "test.recover"


def _definition() -> ToolDefinition:
    return ToolDefinition(
        name=_TOOL_NAME,
        description="Test recoverable input progression.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler_key=_TOOL_NAME,
    )


def _handler(call: ToolCall) -> ToolResult:
    if call.arguments["value"] == "ok":
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success", data={})
    return ToolResult.failure(
        call.call_id,
        call.tool_name,
        "needs_correction",
        "Try a corrected value.",
        model_recovery_required=True,
    )


def _registry():  # type: ignore[no-untyped-def]
    builder = ToolRegistryBuilder()
    builder.register(_definition(), _handler)
    return builder.freeze()


def _call(call_id: str, value: str) -> ModelTurn:
    return ModelTurn(
        tool_calls=(
            ModelToolCall(call_id=call_id, tool_name=_TOOL_NAME, arguments={"value": value}),
        )
    )


def _expand() -> ModelTurn:
    return ModelTurn(
        tool_calls=(
            ModelToolCall(
                call_id="expand",
                tool_name=EXPAND_TOOL_NAME,
                arguments={"tool_names": [_TOOL_NAME]},
            ),
        )
    )


def test_recovery_fingerprint_normalizes_argument_key_order() -> None:
    first = ModelToolCall(
        call_id="one", tool_name="test.tool", arguments={"b": 2, "a": {"z": 1}}
    )
    second = ModelToolCall(
        call_id="two", tool_name="test.tool", arguments={"a": {"z": 1}, "b": 2}
    )
    first_result = ToolResult.failure(
        "one", "test.tool", "recover", "retry", model_recovery_required=True
    )
    second_result = ToolResult.failure(
        "two", "test.tool", "recover", "retry", model_recovery_required=True
    )

    assert _recoverable_failure_fingerprint(first, first_result) == (
        _recoverable_failure_fingerprint(second, second_result)
    )


@pytest.mark.anyio
async def test_changed_recoverable_arguments_continue_beyond_old_turn_count(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _call("bad-1", "one"),
            _call("bad-2", "two"),
            _call("bad-3", "three"),
            _call("bad-4", "four"),
            _call("ok", "ok"),
            ModelTurn(assistant=AssistantMessage(content="Recovered.")),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session, "Keep correcting the input")

    assert outcome.assistant_content == "Recovered."
    for model_call_index in (2, 3, 4, 5):
        assert _TOOL_NAME in {tool.name for tool in backend.calls[model_call_index][1]}


@pytest.mark.anyio
async def test_identical_recoverable_failure_state_eventually_disables_tools(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            _expand(),
            _call("bad-1", "same"),
            _call("bad-2", "same"),
            _call("bad-3", "same"),
            ModelTurn(assistant=AssistantMessage(content="I need corrected input.")),
        ]
    )
    session = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session, "Use the tool")

    assert outcome.assistant_content == "I need corrected input."
    assert backend.calls[-1][1] == ()
    assert any(
        "same recoverable tool failure state" in message.content
        for message in backend.calls[-1][0]
        if message.role == "system"
    )
