from __future__ import annotations

import asyncio

import pytest

from orion.contracts import AssistantDelta, ContextMessage, ModelToolCall, ToolCallDelta
from orion.models.providers.openai_compatible import OpenAICompatibleBackend, _PendingToolCall
from orion.tool_runtime.calculator import calculator_definition


def test_adapter_serializes_tool_result_continuation_without_handler_binding() -> None:
    payload = OpenAICompatibleBackend._message_payload(
        ContextMessage(
            role="assistant",
            content="",
            tool_calls=(
                ModelToolCall(
                    call_id="calc-1",
                    tool_name="calculator.evaluate",
                    arguments={"expression": "2+2"},
                ),
            ),
        )
    )

    assert payload["tool_calls"][0]["function"]["name"] == "calculator.evaluate"
    assert "handler_key" not in str(calculator_definition().provider_schema())


def test_adapter_normalizes_assistant_deltas_and_reconstructs_tool_arguments() -> None:
    backend = OpenAICompatibleBackend()
    content_parts: list[str] = []
    calls: dict[int, _PendingToolCall] = {}

    first = backend._normalize_chunk(
        {"choices": [{"delta": {"content": "I will "}}]}, content_parts, calls
    )
    second = backend._normalize_chunk(
        {"choices": [{"delta": {"content": "calculate."}}]}, content_parts, calls
    )
    tool_start = backend._normalize_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "function": {
                                    "name": "calculator.evaluate",
                                    "arguments": '{"expression":"2',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        content_parts,
        calls,
    )
    tool_end = backend._normalize_chunk(
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '+2"}'}}]}}]},
        content_parts,
        calls,
    )
    turn = backend._build_turn(content_parts, calls)

    assert [event.content for event in first + second if isinstance(event, AssistantDelta)] == [
        "I will ",
        "calculate.",
    ]
    assert isinstance(tool_start[0], ToolCallDelta)
    assert isinstance(tool_end[0], ToolCallDelta)
    assert turn.assistant is not None
    assert turn.assistant.content == "I will calculate."
    assert turn.tool_calls == (
        ModelToolCall(
            call_id="call-1",
            tool_name="calculator.evaluate",
            arguments={"expression": "2+2"},
        ),
    )


@pytest.mark.anyio
async def test_adapter_cancellation_cleans_up_an_active_provider_read() -> None:
    started = asyncio.Event()
    cleaned_up = asyncio.Event()

    class BlockingLines:
        def __aiter__(self) -> BlockingLines:
            return self

        async def __anext__(self) -> str:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned_up.set()
            raise StopAsyncIteration

    cancellation = asyncio.Event()
    task = asyncio.create_task(
        OpenAICompatibleBackend()._next_line_or_cancel(BlockingLines(), cancellation)
    )
    await started.wait()
    cancellation.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned_up.is_set()
