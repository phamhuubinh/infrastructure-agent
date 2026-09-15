from __future__ import annotations

import pytest
from conftest import ScriptedBackend, runtime

from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    RuntimeScope,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.tool_runtime.registry import ToolRegistry, ToolRegistryBuilder
from orion.tool_runtime.runner import ToolRunner


def _definition(name: str, handler_key: str | None = None) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Use {name} for its registered operation.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string", "minLength": 1}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler_key=handler_key or f"internal.{name}",
    )


def _registry(
    names: tuple[str, ...] = ("fake.alpha", "fake.beta"),
    calls: list[ToolCall] | None = None,
) -> ToolRegistry:
    builder = ToolRegistryBuilder()

    def handler(call: ToolCall) -> ToolResult:
        if calls is not None:
            calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"value": call.arguments["value"]},
        )

    for name in names:
        builder.register(_definition(name), handler)
    return builder.freeze()


@pytest.mark.parametrize(
    ("definition", "arguments", "validation_issue"),
    (
        (
            ToolDefinition(
                name="fake.empty",
                description="Take no arguments.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler_key="internal.fake.empty",
            ),
            {"project_id": "wrong"},
            "$: additionalProperties",
        ),
        (_definition("fake.required"), {}, "$: required"),
        (_definition("fake.type"), {"value": 1}, "$.value: type"),
        (
            ToolDefinition(
                name="fake.bounded",
                description="Take a bounded integer.",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "integer", "minimum": 1}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler_key="internal.fake.bounded",
            ),
            {"value": 0},
            "$.value: minimum",
        ),
    ),
)
def test_schema_rejected_arguments_include_structured_model_recovery_diagnostics(
    definition: ToolDefinition, arguments: dict[str, object], validation_issue: str
) -> None:
    dispatched: list[ToolCall] = []
    builder = ToolRegistryBuilder()
    builder.register(definition, lambda call: dispatched.append(call))
    result = ToolRunner(builder.freeze()).run(
        ModelToolCall(call_id="invalid", tool_name=definition.name, arguments=arguments),
        RuntimeScope(session_id="session", principal_id="local", workspace_id="local"),
    )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "invalid_input"
    assert result.error.model_recovery_required
    assert result.error.message == (
        "Tool arguments do not match the registered input schema. "
        f"Validation issue: {validation_issue}. "
        "Retry using only values allowed by the currently exposed schema."
    )
    assert dispatched == []


def test_handler_level_errors_keep_their_existing_recovery_metadata() -> None:
    definition = _definition("fake.semantic")
    builder = ToolRegistryBuilder()
    builder.register(
        definition,
        lambda call: ToolResult.failure(
            call.call_id, call.tool_name, "scope_violation", "Access is denied."
        ),
    )

    result = ToolRunner(builder.freeze()).run(
        ModelToolCall(call_id="semantic", tool_name=definition.name, arguments={"value": "ok"}),
        RuntimeScope(session_id="session", principal_id="local", workspace_id="local"),
    )

    assert result.error is not None
    assert result.error.code == "scope_violation"
    assert not result.error.model_recovery_required


@pytest.mark.anyio
async def test_schema_invalid_call_then_terminal_prose_gets_one_model_chosen_retry(
    store,
) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="invalid",
                        tool_name="fake.alpha",
                        arguments={"value": "retry", "project_id": "wrong"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Project scope may not be bound.")),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="valid", tool_name="fake.alpha", arguments={"value": "retry"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Recovered.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend, _registry(calls=calls)).submit(session_id, "Retry tool")

    assert outcome.assistant_content == "Recovered."
    assert [call.call_id for call in calls] == ["valid"]
    assert len(backend.calls) == 4
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in backend.calls[1][0]
    )
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in backend.calls[2][0]
    )
    results = [
        item.payload["result"]
        for item in store.timeline(session_id)
        if item.kind == "tool_result" and item.tool_name == "fake.alpha"
    ]
    assert results[0]["error"]["model_recovery_required"] is True
    assert results[1]["status"] == "success"


@pytest.mark.anyio
async def test_schema_invalid_call_that_model_immediately_corrects_uses_no_forced_turn(
    store,
) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="invalid",
                        tool_name="fake.alpha",
                        arguments={"value": "retry", "project_id": "wrong"},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="valid", tool_name="fake.alpha", arguments={"value": "retry"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Recovered.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend, _registry(calls=calls)).submit(session_id, "Retry tool")

    assert outcome.assistant_content == "Recovered."
    assert [call.call_id for call in calls] == ["valid"]
    assert len(backend.calls) == 3
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in backend.calls[1][0]
    )


@pytest.mark.anyio
async def test_recovery_decisions_stop_after_the_second_marked_failure(
    store,
) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="invalid-one",
                        tool_name="fake.alpha",
                        arguments={"value": "retry", "project_id": "wrong"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Use the tool again.")),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="invalid-two",
                        tool_name="fake.alpha",
                        arguments={"value": "retry", "project_id": "wrong"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Use the tool again.")),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="invalid-three",
                        tool_name="fake.alpha",
                        arguments={"value": "retry", "project_id": "wrong"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Please clarify.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend, _registry()).submit(session_id, "Retry tool")

    assert outcome.assistant_content == "Please clarify."
    assert len(backend.calls) == 6
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in backend.calls[2][0]
    )
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in backend.calls[4][0]
    )


@pytest.mark.anyio
async def test_two_stage_generic_recovery_chain_preserves_model_tool_choice(store) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    builder = ToolRegistryBuilder()

    def read_handler(call: ToolCall) -> ToolResult:
        calls.append(call)
        return ToolResult.failure(
            call.call_id,
            call.tool_name,
            "not_found",
            "The requested value is unavailable. Obtain an exact value with another tool.",
            model_recovery_required=True,
        )

    def list_handler(call: ToolCall) -> ToolResult:
        calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"values": ["visible-value"]},
        )

    builder.register(_definition("fake.read"), read_handler)
    builder.register(
        ToolDefinition(
            name="fake.list",
            description="List visible values.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler_key="internal.fake.list",
        ),
        list_handler,
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="read", tool_name="fake.read", arguments={"value": "requested"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Call fake.list to recover.")),
            ModelTurn(
                tool_calls=(ModelToolCall(call_id="list", tool_name="fake.list", arguments={}),)
            ),
            ModelTurn(assistant=AssistantMessage(content="Recovered visible value.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend, builder.freeze()).submit(session_id, "Recover")

    assert outcome.assistant_content == "Recovered visible value."
    assert len(backend.calls) == 4
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in backend.calls[1][0]
    )
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in backend.calls[2][0]
    )
    assert [call.tool_name for call in calls] == ["fake.read", "fake.list"]
    assert [
        item.payload["content"]
        for item in store.timeline(session_id)
        if item.kind == "assistant_message" and item.payload["content"]
    ] == [
        "Call fake.list to recover.",
        "Recovered visible value.",
    ]


@pytest.mark.anyio
async def test_actionable_tool_error_keeps_generic_recovery_choices_visible(store) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    builder = ToolRegistryBuilder()

    def alpha_handler(call: ToolCall) -> ToolResult:
        return ToolResult.failure(
            call.call_id,
            call.tool_name,
            "not_found",
            "The requested value is unavailable. Recover with another available tool.",
        )

    def beta_handler(call: ToolCall) -> ToolResult:
        calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"value": call.arguments["value"]},
        )

    builder.register(_definition("fake.alpha"), alpha_handler)
    builder.register(_definition("fake.beta"), beta_handler)
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="alpha", tool_name="fake.alpha", arguments={"value": "missing"}
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="beta", tool_name="fake.beta", arguments={"value": "recovered"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Recovered.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend, builder.freeze()).submit(
        session_id, "Recover the value"
    )

    assert outcome.assistant_content == "Recovered."
    resumed_messages, resumed_tools = backend.calls[1]
    assert "recover safely with registered tools" in resumed_messages[0].content
    assert any(
        "Recover with another available tool." in message.content for message in resumed_messages
    )
    assert resumed_tools == builder.freeze().model_definitions()
    assert backend.calls[0][1] == resumed_tools
    assert [call.tool_name for call in calls] == ["fake.beta"]


@pytest.mark.anyio
async def test_terminal_after_marked_error_gets_one_model_chosen_recovery_decision(
    store,
) -> None:  # type: ignore[no-untyped-def]
    calls: list[ToolCall] = []
    builder = ToolRegistryBuilder()

    def alpha_handler(call: ToolCall) -> ToolResult:
        return ToolResult.failure(
            call.call_id,
            call.tool_name,
            "not_found",
            "The requested value is unavailable. Recover with another available tool.",
            model_recovery_required=True,
        )

    def beta_handler(call: ToolCall) -> ToolResult:
        calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"value": call.arguments["value"]},
        )

    builder.register(_definition("fake.alpha"), alpha_handler)
    builder.register(_definition("fake.beta"), beta_handler)
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="alpha", tool_name="fake.alpha", arguments={"value": "missing"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Call fake.beta to recover.")),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="beta", tool_name="fake.beta", arguments={"value": "recovered"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Recovered.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend, builder.freeze()).submit(
        session_id, "Recover the value"
    )

    assert outcome.assistant_content == "Recovered."
    assert len(backend.calls) == 4
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in backend.calls[2][0]
    )
    recovery_messages, recovery_tools = backend.calls[2]
    assert any(
        "The preceding ToolResult requires recovery" in message.content
        for message in recovery_messages
    )
    assert any("Call fake.beta to recover." in message.content for message in recovery_messages)
    assert recovery_tools == builder.freeze().model_definitions()
    assert backend.calls[0][1] == recovery_tools
    assert [call.tool_name for call in calls] == ["fake.beta"]
    assert [
        item.payload["content"]
        for item in store.timeline(session_id)
        if item.kind == "assistant_message" and item.payload["content"]
    ] == ["Call fake.beta to recover.", "Recovered."]


@pytest.mark.anyio
async def test_non_recoverable_tool_error_can_end_without_an_extra_model_decision(store) -> None:  # type: ignore[no-untyped-def]
    builder = ToolRegistryBuilder()
    builder.register(
        _definition("fake.alpha"),
        lambda call: ToolResult.failure(
            call.call_id, call.tool_name, "unavailable", "The tool is unavailable."
        ),
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="alpha", tool_name="fake.alpha", arguments={"value": "missing"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="I cannot complete that.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend, builder.freeze()).submit(session_id, "Recover")

    assert outcome.assistant_content == "I cannot complete that."
    assert len(backend.calls) == 2


@pytest.mark.anyio
async def test_marked_error_continuation_is_bounded_when_terminal_prose_repeats(store) -> None:  # type: ignore[no-untyped-def]
    builder = ToolRegistryBuilder()
    builder.register(
        _definition("fake.alpha"),
        lambda call: ToolResult.failure(
            call.call_id,
            call.tool_name,
            "not_found",
            "Recoverable failure.",
            model_recovery_required=True,
        ),
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="alpha", tool_name="fake.alpha", arguments={"value": "missing"}
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Call a tool.")),
            ModelTurn(assistant=AssistantMessage(content="Please clarify the request.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend, builder.freeze()).submit(session_id, "Recover")

    assert outcome.assistant_content == "Please clarify the request."
    assert len(backend.calls) == 3
