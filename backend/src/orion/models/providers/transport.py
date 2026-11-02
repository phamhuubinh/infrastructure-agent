"""Bounded provider input and cancellation primitives shared by wire adapters."""

from __future__ import annotations

import asyncio
import codecs
import json
import math
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Any

from orion.models.backend import ModelBackendError, ModelBackendErrorKind

MAX_LINE_BYTES = 262_144
MAX_STREAM_BYTES = 8_388_608


@dataclass(frozen=True)
class SSEEvent:
    name: str
    data: str


async def sse_events(lines: AsyncGenerator[str, None]) -> AsyncGenerator[SSEEvent, None]:
    """Assemble multiline SSE frames; never accept an unterminated final frame."""
    name = "message"
    data: list[str] = []
    size = 0
    try:
        async for line in lines:
            if not line:
                if data:
                    yield SSEEvent(name, "\n".join(data))
                name, data, size = "message", [], 0
                continue
            if line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if not separator:
                value = ""
            if value.startswith(" "):
                value = value[1:]
            if field == "event":
                if len(value) > 128:
                    raise ModelBackendError(
                        "Provider event name exceeds protocol bounds.",
                        kind=ModelBackendErrorKind.MALFORMED_STREAM,
                    )
                name = value or "message"
            elif field == "data":
                size += len(value.encode("utf-8")) + 1
                if size > MAX_LINE_BYTES:
                    raise ModelBackendError(
                        "Provider event exceeds protocol bounds.",
                        kind=ModelBackendErrorKind.MALFORMED_STREAM,
                    )
                data.append(value)
        if data:
            raise ModelBackendError(
                "Provider stream ended inside an event.",
                kind=ModelBackendErrorKind.INCOMPLETE_STREAM,
            )
    finally:
        await lines.aclose()


async def next_or_cancel[T](source: AsyncIterator[T], cancellation: asyncio.Event) -> T | None:
    if cancellation.is_set():
        raise asyncio.CancelledError

    async def read() -> T | None:
        try:
            return await anext(source)
        except StopAsyncIteration:
            return None

    pending = asyncio.create_task(read())
    stopped = asyncio.create_task(cancellation.wait())
    try:
        done, _ = await asyncio.wait({pending, stopped}, return_when=asyncio.FIRST_COMPLETED)
        if stopped in done:
            raise asyncio.CancelledError
        return await pending
    finally:
        for task in (pending, stopped):
            if not task.done():
                task.cancel()
        await asyncio.gather(pending, stopped, return_exceptions=True)


async def bounded_lines(
    chunks: AsyncIterator[bytes],
    cancellation: asyncio.Event,
    *,
    line_limit: int = MAX_LINE_BYTES,
    stream_limit: int = MAX_STREAM_BYTES,
) -> AsyncGenerator[str, None]:
    """Decode strict UTF-8 and cap input before accumulating unbounded lines.

    Callers supply HTTPX's fixed-size decoded byte iterator, so compressed input
    is bounded after decompression as well. CR, LF and split CRLF are accepted.
    """
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending = ""
    line_bytes = total = 0
    after_cr = False
    try:
        while True:
            chunk = await next_or_cancel(chunks, cancellation)
            if chunk is None:
                text = decoder.decode(b"", final=True)
            else:
                total += len(chunk)
                if total > stream_limit:
                    raise ValueError("provider stream exceeds byte limit")
                text = decoder.decode(chunk)
            # Scan delimiters once; avoid quadratic per-character concatenation.
            start = 0
            for index, character in enumerate(text):
                if after_cr:
                    after_cr = False
                    if character == "\n":
                        start = index + 1
                        continue
                if character in "\r\n":
                    segment = text[start:index]
                    line_bytes += len(segment.encode("utf-8"))
                    if line_bytes > line_limit:
                        raise ValueError("provider line exceeds byte limit")
                    yield pending + segment
                    pending = ""
                    line_bytes = 0
                    after_cr = character == "\r"
                    start = index + 1
            tail = text[start:]
            line_bytes += len(tail.encode("utf-8"))
            if line_bytes > line_limit:
                raise ValueError("provider line exceeds byte limit")
            pending += tail
            if chunk is None:
                if pending:
                    yield pending
                return
    except (ValueError, UnicodeError):
        raise ModelBackendError(
            "Provider stream encoding or byte limits are invalid.",
            kind=ModelBackendErrorKind.MALFORMED_STREAM,
        ) from None
    finally:
        close = getattr(chunks, "aclose", None)
        if close is not None:
            await close()


def strict_json(value: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = item
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError("non-finite JSON number")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite JSON number")
        return number

    return json.loads(
        value,
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
        parse_float=finite_float,
    )
