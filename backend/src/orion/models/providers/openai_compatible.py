"""OpenAI-compatible/local streaming chat-completions adapter."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any

import httpx

from orion.contracts import (
    ContextMessage,
    ModelTurnCompleted,
    ModelUsage,
    ToolDefinition,
    freeze_json,
)
from orion.models.backend import (
    ModelBackend,
    ModelBackendError,
    ModelBackendErrorKind,
    ModelSettings,
    ModelStreamEvent,
    ModelStreamSettings,
)
from orion.models.providers.chat_completions import (
    ChatCompletionsDecoder,
)
from orion.models.providers.chat_completions import (
    PendingToolCall as _PendingToolCall,
)
from orion.models.providers.transport import (
    SSEEvent,
    bounded_lines,
    next_or_cancel,
    sse_events,
)


class OpenAICompatibleBackend(ChatCompletionsDecoder, ModelBackend):
    def validate_settings(self, settings: ModelSettings) -> None:
        if settings.provider_type != "openai_compatible":
            raise ModelBackendError(
                "This adapter only supports explicitly compatible profiles.",
                kind=ModelBackendErrorKind.UNSUPPORTED,
            )
        if (
            settings.reasoning_mode != "auto"
            and os.getenv("ORION_OPENAI_COMPAT_REASONING_TEMPLATE_KWARGS") != "1"
        ):
            raise ModelBackendError(
                "The compatible server has no configured reasoning control support.",
                kind=ModelBackendErrorKind.UNSUPPORTED,
            )

    def __init__(self, stream_settings: ModelStreamSettings | None = None) -> None:
        self._cached_tools: tuple[ToolDefinition, ...] | None = None
        self._cached_provider_tools: tuple[dict[str, Any], ...] = ()
        self._stream_settings = stream_settings or ModelStreamSettings.from_environment()

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
        self.validate_settings(settings)
        headers = {"Content-Type": "application/json"}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        payload: dict[str, Any] = {
            "model": settings.model_id,
            "messages": self._provider_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        configured_temperature = os.getenv("ORION_MODEL_TEMPERATURE")
        if configured_temperature is not None:
            payload["temperature"] = float(configured_temperature)
        if (
            settings.reasoning_mode != "auto"
            and os.getenv("ORION_OPENAI_COMPAT_REASONING_TEMPLATE_KWARGS") == "1"
        ):
            payload.setdefault("chat_template_kwargs", {})["enable_thinking"] = (
                settings.reasoning_mode == "enabled"
            )
        if tools:
            payload["tools"] = self._provider_tools(tools)
        url = f"{settings.base_url.rstrip('/')}/chat/completions"
        content_parts: list[str] = []
        calls: dict[int, _PendingToolCall] = {}
        usage: ModelUsage | None = None
        stream_finished = False
        response_started = False
        try:
            timeout = self._stream_settings.timeout_seconds
            if settings.profile is not None:
                timeout = settings.profile.transport_timeout_seconds
                encoded = json.dumps(
                    payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
                if len(encoded) > settings.profile.request_max_bytes:
                    raise ModelBackendError(
                        "Model request exceeds the configured profile byte limit.",
                        kind=ModelBackendErrorKind.UNSUPPORTED,
                    )
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    response_started = True
                    response.raise_for_status()
                    async with aclosing(
                        sse_events(
                            bounded_lines(response.aiter_bytes(chunk_size=16_384), cancellation)
                        )
                    ) as frames:
                        while True:
                            frame = await self._next_frame_or_cancel(frames, cancellation)
                            if frame is None:
                                break
                            raw_chunk = frame.data.strip()
                            if raw_chunk == "[DONE]":
                                stream_finished = True
                                break
                            if not raw_chunk:
                                continue
                            chunk = self._parse_chunk(raw_chunk)
                            self._raise_for_stream_error(chunk)
                            was_finished = stream_finished
                            stream_finished = (
                                self._chunk_has_finish_reason(chunk) or stream_finished
                            )
                            chunk_usage = self._usage_from_chunk(chunk)
                            if chunk_usage is not None:
                                usage = chunk_usage
                            normalized = tuple(self._normalize_chunk(chunk, content_parts, calls))
                            if was_finished and normalized:
                                raise ModelBackendError(
                                    "Provider emitted content after completing the turn.",
                                    kind=ModelBackendErrorKind.PROTOCOL,
                                )
                            for event in normalized:
                                yield event
            if not stream_finished:
                raise ModelBackendError(
                    "OpenAI-compatible model stream ended before completion.",
                    kind=ModelBackendErrorKind.INCOMPLETE_STREAM,
                )
        except asyncio.CancelledError:
            raise
        except ModelBackendError:
            raise
        except httpx.HTTPError as error:
            classified = self._transport_error(error)
            if response_started:
                classified.retry_safe = False
            raise classified from error
        except ValueError as error:
            raise ModelBackendError(
                "OpenAI-compatible model stream was malformed.",
                kind=ModelBackendErrorKind.MALFORMED_STREAM,
            ) from error

        yield ModelTurnCompleted(turn=self._build_turn(content_parts, calls), usage=usage)

    async def _next_line_or_cancel(
        self, lines: AsyncIterator[str], cancellation: asyncio.Event
    ) -> str | None:
        return await next_or_cancel(lines, cancellation)

    async def _next_frame_or_cancel(
        self, frames: AsyncIterator[SSEEvent], cancellation: asyncio.Event
    ) -> SSEEvent | None:
        return await next_or_cancel(frames, cancellation)

    @staticmethod
    def _transport_error(error: httpx.HTTPError) -> ModelBackendError:
        if isinstance(error, httpx.TimeoutException):
            return ModelBackendError(
                "OpenAI-compatible model stream timed out.",
                kind=ModelBackendErrorKind.TIMEOUT,
                retry_safe=isinstance(error, httpx.ConnectTimeout),
            )
        if isinstance(error, httpx.HTTPStatusError):
            return ModelBackendError(
                "OpenAI-compatible model returned an HTTP error.",
                kind=ModelBackendErrorKind.UPSTREAM_HTTP,
            )
        if isinstance(error, httpx.ProtocolError):
            return ModelBackendError(
                "OpenAI-compatible model stream encountered a protocol error.",
                kind=ModelBackendErrorKind.PROTOCOL,
            )
        if isinstance(error, httpx.NetworkError):
            return ModelBackendError(
                "OpenAI-compatible model connection failed.",
                kind=ModelBackendErrorKind.CONNECTION,
                retry_safe=isinstance(error, httpx.ConnectError),
            )
        return ModelBackendError("OpenAI-compatible model stream failed.")

    @staticmethod
    def _provider_messages(messages: tuple[ContextMessage, ...]) -> list[dict[str, Any]]:
        """Emit the minimum portable OpenAI message sequence.

        One system instruction is permitted only at the front. This is enforced
        for every OpenAI-compatible server, not by model-name detection.
        """
        seen_conversation = False
        system_count = 0
        for message in messages:
            if message.role == "system":
                system_count += 1
                if seen_conversation or system_count > 1:
                    raise ModelBackendError(
                        "Model input contains a system message after conversation began.",
                        kind=ModelBackendErrorKind.PROTOCOL,
                    )
            else:
                seen_conversation = True
        return [OpenAICompatibleBackend._message_payload(message) for message in messages]

    @staticmethod
    def _message_payload(message: ContextMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.role == "assistant" and message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.tool_name,
                        "arguments": json.dumps(call.arguments, separators=(",", ":")),
                    },
                }
                for call in message.tool_calls
            ]
        if message.role == "tool":
            payload["tool_call_id"] = message.tool_call_id
            payload["name"] = message.tool_name
        return payload

    def _provider_tools(self, tools: tuple[ToolDefinition, ...]) -> list[dict[str, Any]]:
        if tools is not self._cached_tools:
            self._cached_tools = tools
            self._cached_provider_tools = tuple(
                freeze_json(definition.provider_schema()) for definition in tools
            )
        # Only the outer request list is copied. Every cached nested JSON object is
        # immutable, so a caller cannot corrupt later model turns.
        return list(self._cached_provider_tools)
