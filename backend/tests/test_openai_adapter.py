from __future__ import annotations

import asyncio

import pytest

from orion.contracts import (
    AssistantDelta,
    ContextMessage,
    ModelToolCall,
    ModelTurnCompleted,
    ToolCallDelta,
)
from orion.models.backend import ModelBackendError, ModelSettings
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


@pytest.mark.parametrize(
    "marker",
    (
        "[[source:abc]]",
        "[[source: abc]]",
        "[[source:abc ]]",
        "[[source: abc ]]",
    ),
)
def test_adapter_normalizes_insignificant_citation_marker_whitespace(marker: str) -> None:
    turn = OpenAICompatibleBackend._build_turn([f"Answer. {marker}"], {})

    assert turn.assistant is not None
    assert turn.assistant.content == f"Answer. {marker}"
    assert turn.assistant.citation_source_ref_ids == ("abc",)


@pytest.mark.anyio
async def test_adapter_requests_and_normalizes_stream_usage(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self):  # type: ignore[no-untyped-def]
            yield 'data: {"choices":[{"delta":{"content":"Answer."}}]}'
            yield 'data: {"choices":[],"usage":{"prompt_tokens":1824,"completion_tokens":216}}'
            yield "data: [DONE]"

    class Stream:
        async def __aenter__(self) -> Response:
            return Response()

        async def __aexit__(self, *args: object) -> None:
            return None

    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> Stream:
            captured.update({"method": method, "url": url, **kwargs})
            return Stream()

    monkeypatch.setattr(
        "orion.models.providers.openai_compatible.httpx.AsyncClient", lambda **_: Client()
    )
    events = [
        event
        async for event in OpenAICompatibleBackend().stream(
            (ContextMessage(role="user", content="Hello"),),
            (),
            ModelSettings(
                provider_type="openai_compatible",
                base_url="http://model.test/v1",
                model_id="fake",
            ),
            asyncio.Event(),
        )
    ]

    assert captured["method"] == "POST"
    assert captured["url"] == "http://model.test/v1/chat/completions"
    assert captured["json"] == {
        "model": "fake",
        "messages": [{"role": "user", "content": "Hello"}],
        "tools": [],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    completed = events[-1]
    assert isinstance(completed, ModelTurnCompleted)
    assert completed.usage is not None
    assert completed.usage.input_tokens == 1824
    assert completed.usage.output_tokens == 216


@pytest.mark.anyio
async def test_adapter_rejects_malformed_stream_usage(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class Response:
        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self):  # type: ignore[no-untyped-def]
            yield 'data: {"choices":[],"usage":{"prompt_tokens":-1,"completion_tokens":216}}'

    class Stream:
        async def __aenter__(self) -> Response:
            return Response()

        async def __aexit__(self, *args: object) -> None:
            return None

    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def stream(self, *args: object, **kwargs: object) -> Stream:
            return Stream()

    monkeypatch.setattr(
        "orion.models.providers.openai_compatible.httpx.AsyncClient", lambda **_: Client()
    )

    with pytest.raises(ModelBackendError, match="OpenAI-compatible model stream failed"):
        async for _ in OpenAICompatibleBackend().stream(
            (ContextMessage(role="user", content="Hello"),),
            (),
            ModelSettings(
                provider_type="openai_compatible",
                base_url="http://model.test/v1",
                model_id="fake",
            ),
            asyncio.Event(),
        ):
            pass


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
