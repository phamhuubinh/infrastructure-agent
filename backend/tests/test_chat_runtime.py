from __future__ import annotations

import asyncio

import pytest
from conftest import ScriptedBackend, runtime

from orion.chat.context_builder import ContextBuilder
from orion.chat.runtime import RequestCancelled, RequestFailed
from orion.contracts import (
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.models.backend import ModelBackend, ModelBackendError, ModelSettings
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.tool_runtime.registry import ToolRegistryBuilder


@pytest.mark.anyio
async def test_direct_answer_executes_no_tool(store) -> None:  # type: ignore[no-untyped-def]
    executions = 0

    def counted_tool(call: ToolCall) -> ToolResult:
        nonlocal executions
        executions += 1
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success", data={})

    registry_builder = ToolRegistryBuilder()
    registry_builder.register(
        ToolDefinition(
            name="fake.count",
            description="Counter.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler_key="fake.count",
        ),
        counted_tool,
    )
    registry = registry_builder.freeze()
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Direct answer."))])
    session_id = store.create_session()

    outcome = await runtime(store, backend, registry).submit(session_id, "Hello")

    assert outcome.assistant_content == "Direct answer."
    assert executions == 0
    assert len(backend.calls) == 1
    assert [definition.name for definition in backend.calls[0][1]] == ["fake.count"]


@pytest.mark.anyio
async def test_adapter_parsed_whitespace_citation_is_rejected_when_not_visible(
    store,
) -> None:  # type: ignore[no-untyped-def]
    turn = OpenAICompatibleBackend._build_turn(["Unsupported citation. [[source: none]]"], {})
    assert turn.assistant is not None
    assert turn.assistant.citation_source_ref_ids == ("none",)
    backend = ScriptedBackend([turn])
    session_id = store.create_session()

    with pytest.raises(RequestFailed, match="unavailable source"):
        await runtime(store, backend).submit(session_id, "Answer")


@pytest.mark.anyio
async def test_assistant_deltas_are_public_but_persist_one_final_message(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [ModelTurn(assistant=AssistantMessage(content="Streamed answer."))],
        deltas=[["Streamed ", "answer."]],
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend).submit(session_id, "Stream this")

    assert [event["type"] for event in store.events(outcome.request_id)] == [
        "request.accepted",
        "model.started",
        "assistant.delta",
        "assistant.delta",
        "model.completed",
        "assistant.message",
        "request.completed",
    ]
    assistant_items = [
        item for item in store.timeline(session_id) if item.kind == "assistant_message"
    ]
    assert len(assistant_items) == 1
    assert assistant_items[0].payload["content"] == "Streamed answer."


@pytest.mark.anyio
async def test_calculator_round_trip_returns_to_same_model(store) -> None:  # type: ignore[no-untyped-def]
    backend = ScriptedBackend(
        [
            ModelTurn(
                assistant=AssistantMessage(content="Calculating. "),
                tool_calls=(
                    ModelToolCall(
                        call_id="calc-1",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "2 + 3"},
                    ),
                ),
            ),
            ModelTurn(assistant=AssistantMessage(content="The result is 5.")),
        ],
        deltas=[["Calculating. "], ["The result ", "is 5."]],
    )
    session_id = store.create_session()

    outcome = await runtime(store, backend).submit(session_id, "What is 2 + 3?")

    assert outcome.assistant_content == "The result is 5."
    assert len(backend.calls) == 2
    continuation = backend.calls[1][0]
    assert continuation[-1].role == "tool"
    assert '"value":5' in continuation[-1].content
    assert '"sources":[]' in continuation[-1].content
    calculator_result = ToolResult.model_validate_json(continuation[-1].content)
    assert calculator_result.sources == ()
    assert [event["type"] for event in store.events(outcome.request_id)] == [
        "request.accepted",
        "model.started",
        "assistant.delta",
        "model.completed",
        "assistant.message",
        "tool.started",
        "tool.completed",
        "model.resumed",
        "model.started",
        "assistant.delta",
        "assistant.delta",
        "model.completed",
        "assistant.message",
        "request.completed",
    ]
    assert [item.kind for item in store.timeline(session_id)] == [
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
        "assistant_message",
    ]


def test_context_builder_explains_source_less_tool_results_cannot_be_cited(
    store,
) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()

    instructions = ContextBuilder(store).build(session_id)[0].content

    assert "exact source_ref_id from a ToolResult.sources entry visible" in instructions
    assert "sources=[], do not emit any [[source:...]] marker" in instructions
    assert "Never invent, guess, transform, or reuse a source_ref_id" in instructions


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
    async def stream(self, messages, tools, settings: ModelSettings, cancellation):  # type: ignore[no-untyped-def]
        await cancellation.wait()
        raise asyncio.CancelledError
        if False:
            yield None


class FailingBackend(ModelBackend):
    async def stream(self, messages, tools, settings: ModelSettings, cancellation):  # type: ignore[no-untyped-def]
        raise ModelBackendError("Model unavailable.")
        if False:
            yield None


class ExplodingBackend(ModelBackend):
    async def stream(self, messages, tools, settings: ModelSettings, cancellation):  # type: ignore[no-untyped-def]
        raise RuntimeError("internal credential=do-not-expose")
        if False:
            yield None


class SerializedBackend(ModelBackend):
    def __init__(self) -> None:
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()
        self.contexts = []
        self.calls = 0

    async def stream(self, messages, tools, settings: ModelSettings, cancellation):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.contexts.append(messages)
        if self.calls == 1:
            self.first_started.set()
            await self.release_first.wait()
            from orion.contracts import ModelTurnCompleted

            yield ModelTurnCompleted(
                turn=ModelTurn(assistant=AssistantMessage(content="First answer."))
            )
            return
        from orion.contracts import ModelTurnCompleted

        yield ModelTurnCompleted(
            turn=ModelTurn(assistant=AssistantMessage(content="Second answer."))
        )


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


@pytest.mark.anyio
async def test_unexpected_runtime_failure_is_terminal_and_redacted(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    chat = runtime(store, ExplodingBackend())
    request_id = chat.begin(session_id, "Hello")

    with pytest.raises(RequestFailed, match="Request failed unexpectedly"):
        await chat.run(session_id, request_id)

    request = store.request(request_id)
    assert request is not None
    assert request["status"] == "failed"
    assert request["error_message"] == "Request failed unexpectedly."
    events = store.events(request_id)
    assert events[-1] == {
        "type": "request.failed",
        "created_at": events[-1]["created_at"],
        "payload": {"message": "Request failed unexpectedly."},
    }
    assert "credential" not in str(events)


@pytest.mark.anyio
async def test_requests_in_one_session_are_serialized_before_context_assembly(store) -> None:  # type: ignore[no-untyped-def]
    session_id = store.create_session()
    backend = SerializedBackend()
    chat = runtime(store, backend)

    first = asyncio.create_task(chat.submit(session_id, "First question"))
    await backend.first_started.wait()
    second = asyncio.create_task(chat.submit(session_id, "Second question"))
    await asyncio.sleep(0)
    backend.release_first.set()

    first_outcome, second_outcome = await asyncio.gather(first, second)

    assert first_outcome.assistant_content == "First answer."
    assert second_outcome.assistant_content == "Second answer."
    assert [message.content for message in backend.contexts[0] if message.role == "user"] == [
        "First question"
    ]
    assert [message.content for message in backend.contexts[1] if message.role == "user"] == [
        "First question",
        "Second question",
    ]
    assert [item.kind for item in store.timeline(session_id)] == [
        "user_message",
        "assistant_message",
        "user_message",
        "assistant_message",
    ]
