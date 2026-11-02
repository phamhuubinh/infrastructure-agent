from __future__ import annotations

import asyncio

import pytest

from orion.models.backend import ModelBackendError
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.models.providers.transport import bounded_lines, next_or_cancel, sse_events, strict_json


@pytest.mark.anyio
@pytest.mark.parametrize("size", [1, 2, 3, 7, 100])
async def test_bounded_decoder_preserves_unicode_and_split_crlf(size):
    data = "data: Xin chào 秘\r\n\rnext\nlast".encode()

    async def source():
        for offset in range(0, len(data), size):
            yield data[offset : offset + size]

    assert [line async for line in bounded_lines(source(), asyncio.Event())] == [
        "data: Xin chào 秘",
        "",
        "next",
        "last",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "chunks,limits",
    [
        ([b"123", b"456"], {"line_limit": 5}),
        ([b"12\n", b"34\n"], {"stream_limit": 5}),
        ([b"\xff"], {}),
        ([b"\xe2\x82"], {}),
    ],
)
async def test_malformed_or_oversized_stream_fails_and_closes_source(chunks, limits):
    closed = []

    async def source():
        try:
            for chunk in chunks:
                yield chunk
        finally:
            closed.append(True)

    with pytest.raises(ModelBackendError, match="encoding or byte limits"):
        _ = [line async for line in bounded_lines(source(), asyncio.Event(), **limits)]
    assert closed == [True]


@pytest.mark.anyio
@pytest.mark.parametrize("signal", [True, False])
async def test_signal_or_parent_task_cancel_awaits_active_read_cleanup(signal):
    started, closed, cancellation = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def source():
        try:
            started.set()
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            closed.set()

    task = asyncio.create_task(next_or_cancel(source(), cancellation))
    await started.wait()
    if signal:
        cancellation.set()
    else:
        task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.parametrize(
    "payload",
    ['{"x":1,"x":2}', '{"nested":{"x":1,"x":2}}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}'],
)
def test_strict_json_rejects_ambiguous_and_nonfinite_arguments(payload):
    with pytest.raises(ValueError):
        strict_json(payload)


@pytest.mark.parametrize("reason", ["length", "content_filter", "unknown", ""])
def test_incomplete_finish_reason_cannot_authorize_tool_dispatch(reason):
    with pytest.raises(ModelBackendError, match="truncated, filtered"):
        OpenAICompatibleBackend._chunk_has_finish_reason({"choices": [{"finish_reason": reason}]})


@pytest.mark.anyio
async def test_sse_multiline_events_comments_and_unicode_across_byte_boundaries():
    payload = ': ping\r\nevent: response.delta\r\ndata: {"text":\r\ndata: "秘"}\r\n\r\n'

    async def source():
        for byte in payload.encode():
            yield bytes([byte])

    events = [event async for event in sse_events(bounded_lines(source(), asyncio.Event()))]
    assert len(events) == 1
    assert events[0].name == "response.delta"
    assert strict_json(events[0].data) == {"text": "秘"}


@pytest.mark.anyio
async def test_sse_eof_does_not_promote_partial_terminal_frame():
    async def source():
        yield b'data: {"type":"completed"}\n'

    with pytest.raises(ModelBackendError, match="inside an event"):
        _ = [event async for event in sse_events(bounded_lines(source(), asyncio.Event()))]
