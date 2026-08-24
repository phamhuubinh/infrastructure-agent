from __future__ import annotations

import asyncio

import pytest
from conftest import ScriptedBackend, runtime

from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.models.backend import ModelBackend, ModelBackendError, ModelSettings
from orion.runtime.chat_runtime import RequestCancelled, RequestFailed
from orion.tools.registry import ToolRegistry


@pytest.mark.anyio
async def test_direct_answer_executes_no_tool(store) -> None:  # type: ignore[no-untyped-def]
    executions = 0

    def counted_tool(call: ToolCall) -> ToolResult:
        nonlocal executions
        executions += 1
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success", data={})

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="fake.count",
            description="Counter.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler_key="fake.count",
        ),
        counted_tool,
    )
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Direct answer."))])
    session_id = store.create_session()

    outcome = await runtime(store, backend, registry).submit(session_id, "Hello")

    assert outcome.assistant_content == "Direct answer."
    assert executions == 0
    assert len(backend.calls) == 1
    assert [definition.name for definition in backend.calls[0][1]] == ["fake.count"]


@pytest.mark.anyio
async def test_calculator_round_trip_returns_to_same_model(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                assistant=AssistantMessage(),
                tool_calls=(
                    ModelToolCall(
                        call_id="calc-1",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "2 + 3"},
                    ),
                ),
            ),
            ModelTurn(assistant=AssistantMessage(content="The result is 5.")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend).submit(session_id, "What is 2 + 3?")

    assert outcome.assistant_content == "The result is 5."
    assert len(backend.calls) == 2
    continuation = backend.calls[1][0]
    assert continuation[-1].role == "tool"
    assert '"value":5' in continuation[-1].content
    assert [item.kind for item in store.timeline(session_id)] == [
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
        "assistant_message",
    ]


@pytest.mark.anyio
async def test_sequential_calculator_calls_have_no_orion_call_quota(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="one",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "1 + 1"},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="two",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "2 * 3"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="2 and 6")),
        ]
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend).submit(session_id, "Use two calculations")

    assert outcome.assistant_content == "2 and 6"
    assert len(backend.calls) == 3


@pytest.mark.anyio
async def test_assistant_content_and_tool_call_are_preserved_in_one_turn(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                assistant=AssistantMessage(content="I will calculate that."),
                tool_calls=(
                    ModelToolCall(
                        call_id="one",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "4 / 2"},
                    ),
                ),
            ),
            ModelTurn(assistant=AssistantMessage(content="It is 2.")),
        ]
    )
    session_id = store.create_session()

    await runtime(store, backend).submit(session_id, "Calculate")

    first_assistant = store.timeline(session_id)[1]
    assert first_assistant.payload["content"] == "I will calculate that."
    assert first_assistant.payload["tool_calls"][0]["call_id"] == "one"
    assert backend.calls[1][0][-2].content == "I will calculate that."
    assert backend.calls[1][0][-2].tool_calls[0].tool_name == "calculator.evaluate"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name,arguments,error_code",
    [
        ("missing.tool", {}, "not_found"),
        ("calculator.evaluate", {"expression": 4}, "invalid_input"),
    ],
)
async def test_unknown_or_invalid_tools_never_dispatch(
    store, tool_name, arguments, error_code
) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(ModelToolCall(call_id="bad", tool_name=tool_name, arguments=arguments),)
            ),
            ModelTurn(assistant=AssistantMessage(content="I could not run that tool.")),
        ]
    )
    session_id = store.create_session()

    await runtime(store, backend).submit(session_id, "Try it")

    tool_result = store.timeline(session_id)[3].payload["result"]
    assert tool_result["status"] == "error"
    assert tool_result["error"]["code"] == error_code


class BlockingBackend(ModelBackend):
    async def complete(self, messages, tools, settings: ModelSettings, cancellation) -> ModelTurn:  # type: ignore[no-untyped-def]
        await cancellation.wait()
        raise asyncio.CancelledError


class FailingBackend(ModelBackend):
    async def complete(self, messages, tools, settings: ModelSettings, cancellation) -> ModelTurn:  # type: ignore[no-untyped-def]
        raise ModelBackendError("Model unavailable.")


@pytest.mark.anyio
async def test_runtime_cancellation_is_persisted(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    chat = runtime(store, BlockingBackend())
    request_id = chat.begin(session_id, "Wait")
    task = asyncio.create_task(chat.run(session_id, request_id))
    await asyncio.sleep(0)
    assert chat.cancel(request_id)

    with pytest.raises(RequestCancelled):
        await task
    assert store.request(request_id)["status"] == "cancelled"


@pytest.mark.anyio
async def test_runtime_model_failure_is_persisted(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    with pytest.raises(RequestFailed, match="Model unavailable"):
        await runtime(store, FailingBackend()).submit(session_id, "Hello")
    assert [item.kind for item in store.timeline(session_id)] == ["user_message"]
