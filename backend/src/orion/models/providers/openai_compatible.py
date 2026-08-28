"""OpenAI-compatible/local streaming chat-completions adapter."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ContextMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ToolCallDelta,
    ToolDefinition,
)
from orion.models.backend import ModelBackend, ModelBackendError, ModelSettings, ModelStreamEvent


@dataclass
class _PendingToolCall:
    call_id: str = ""
    tool_name: str = ""
    arguments: str = ""


class OpenAICompatibleBackend(ModelBackend):
    async def stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        """Translate provider SSE chunks without exposing native provider objects."""
        if cancellation.is_set():
            raise asyncio.CancelledError
        headers = {"Content-Type": "application/json"}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        payload = {
            "model": settings.model_id,
            "messages": [self._message_payload(message) for message in messages],
            "tools": [definition.provider_schema() for definition in tools],
            "stream": True,
        }
        url = f"{settings.base_url.rstrip('/')}/chat/completions"
        content_parts: list[str] = []
        calls: dict[int, _PendingToolCall] = {}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    lines = response.aiter_lines().__aiter__()
                    while True:
                        line = await self._next_line_or_cancel(lines, cancellation)
                        if line is None:
                            break
                        if not line.startswith("data:"):
                            continue
                        raw_chunk = line[5:].strip()
                        if raw_chunk == "[DONE]":
                            break
                        if not raw_chunk:
                            continue
                        chunk = self._parse_chunk(raw_chunk)
                        for event in self._normalize_chunk(chunk, content_parts, calls):
                            yield event
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            raise ModelBackendError("OpenAI-compatible model stream failed.") from error

        yield ModelTurnCompleted(turn=self._build_turn(content_parts, calls))

    async def _next_line_or_cancel(
        self, lines: AsyncIterator[str], cancellation: asyncio.Event
    ) -> str | None:
        async def next_or_none() -> str | None:
            try:
                return await anext(lines)
            except StopAsyncIteration:
                return None

        async def cancellation_signal() -> str | None:
            await cancellation.wait()
            return None

        next_line = asyncio.create_task(next_or_none())
        cancelled = asyncio.create_task(cancellation_signal())
        done, _ = await asyncio.wait({next_line, cancelled}, return_when=asyncio.FIRST_COMPLETED)
        if cancelled in done:
            next_line.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await next_line
            raise asyncio.CancelledError
        cancelled.cancel()
        return await next_line

    @staticmethod
    def _parse_chunk(raw_chunk: str) -> dict[str, Any]:
        chunk = json.loads(raw_chunk)
        if not isinstance(chunk, dict):
            raise ValueError("provider stream chunk is not an object")
        return chunk

    def _normalize_chunk(
        self,
        chunk: dict[str, Any],
        content_parts: list[str],
        calls: dict[int, _PendingToolCall],
    ) -> tuple[AssistantDelta | ToolCallDelta, ...]:
        try:
            choices = chunk.get("choices", [])
            if not choices:
                return ()
            delta = choices[0].get("delta", {})
            if not isinstance(delta, dict):
                raise ValueError("provider stream delta is not an object")
            events: list[AssistantDelta | ToolCallDelta] = []
            content = delta.get("content")
            if content is not None:
                if not isinstance(content, str):
                    raise ValueError("assistant delta is not a string")
                if content:
                    content_parts.append(content)
                    events.append(AssistantDelta(content=content))
            raw_calls = delta.get("tool_calls") or []
            if not isinstance(raw_calls, list):
                raise ValueError("tool call deltas are not a list")
            for raw_call in raw_calls:
                if not isinstance(raw_call, dict):
                    raise ValueError("tool call delta is not an object")
                index = raw_call.get("index", 0)
                if not isinstance(index, int) or index < 0:
                    raise ValueError("tool call delta index is invalid")
                pending = calls.setdefault(index, _PendingToolCall())
                call_id = raw_call.get("id")
                if call_id is not None:
                    if not isinstance(call_id, str):
                        raise ValueError("tool call ID is invalid")
                    pending.call_id += call_id
                function = raw_call.get("function") or {}
                if not isinstance(function, dict):
                    raise ValueError("tool call function delta is invalid")
                tool_name = function.get("name")
                if tool_name is not None:
                    if not isinstance(tool_name, str):
                        raise ValueError("tool name is invalid")
                    pending.tool_name += tool_name
                arguments_delta = function.get("arguments")
                if arguments_delta is not None:
                    if not isinstance(arguments_delta, str):
                        raise ValueError("tool arguments delta is invalid")
                    pending.arguments += arguments_delta
                events.append(
                    ToolCallDelta(
                        index=index,
                        call_id=call_id,
                        tool_name=tool_name,
                        arguments_delta=arguments_delta or "",
                    )
                )
            return tuple(events)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
            raise ModelBackendError("Model returned an invalid streaming response.") from error

    @staticmethod
    def _build_turn(content_parts: list[str], calls: dict[int, _PendingToolCall]) -> ModelTurn:
        try:
            tool_calls: list[ModelToolCall] = []
            for index in sorted(calls):
                pending = calls[index]
                if not pending.call_id or not pending.tool_name:
                    raise ValueError("streamed tool call is incomplete")
                arguments = json.loads(pending.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("tool arguments are not an object")
                tool_calls.append(
                    ModelToolCall(
                        call_id=pending.call_id,
                        tool_name=pending.tool_name,
                        arguments=arguments,
                    )
                )
            content = "".join(content_parts)
            citations = tuple(re.findall(r"\[\[source:\s*([^\]\s]+)\s*\]\]", content))
            assistant = None
            if content:
                assistant = AssistantMessage(content=content, citation_source_ref_ids=citations)
            return ModelTurn(assistant=assistant, tool_calls=tuple(tool_calls))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ModelBackendError("Model returned an invalid streaming response.") from error

    @staticmethod
    def _message_payload(message: ContextMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.role == "assistant" and message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.tool_name, "arguments": json.dumps(call.arguments)},
                }
                for call in message.tool_calls
            ]
        if message.role == "tool":
            payload["tool_call_id"] = message.tool_call_id
            payload["name"] = message.tool_name
        return payload
