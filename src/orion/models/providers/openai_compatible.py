"""OpenAI-compatible/local chat-completions adapter."""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import httpx

from orion.contracts import (
    AssistantMessage,
    ContextMessage,
    ModelToolCall,
    ModelTurn,
    ToolDefinition,
)
from orion.models.backend import ModelBackend, ModelBackendError, ModelSettings


class OpenAICompatibleBackend(ModelBackend):
    async def complete(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> ModelTurn:
        if cancellation.is_set():
            raise asyncio.CancelledError
        headers = {"Content-Type": "application/json"}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        payload = {
            "model": settings.model_id,
            "messages": [self._message_payload(message) for message in messages],
            "tools": [definition.provider_schema() for definition in tools],
        }
        url = f"{settings.base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                request = client.post(url, headers=headers, json=payload)
                response = await self._await_or_cancel(request, cancellation)
                response.raise_for_status()
                native_response: dict[str, Any] = response.json()
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise ModelBackendError("OpenAI-compatible model request failed.") from error
        return self._normalize(native_response)

    async def _await_or_cancel(self, request: Any, cancellation: asyncio.Event) -> httpx.Response:
        request_task = asyncio.create_task(request)
        cancellation_task = asyncio.create_task(cancellation.wait())
        done, _ = await asyncio.wait(
            {request_task, cancellation_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if cancellation_task in done:
            request_task.cancel()
            raise asyncio.CancelledError
        cancellation_task.cancel()
        return cast(httpx.Response, await request_task)

    def _message_payload(self, message: ContextMessage) -> dict[str, Any]:
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

    def _normalize(self, response: dict[str, Any]) -> ModelTurn:
        try:
            message = response["choices"][0]["message"]
            content = message.get("content") or ""
            calls: list[ModelToolCall] = []
            for call in message.get("tool_calls") or []:
                function = call["function"]
                raw_arguments = function.get("arguments", "{}")
                arguments = (
                    raw_arguments if isinstance(raw_arguments, dict) else json.loads(raw_arguments)
                )
                if not isinstance(arguments, dict):
                    raise ValueError("tool arguments are not an object")
                calls.append(
                    ModelToolCall(
                        call_id=call["id"], tool_name=function["name"], arguments=arguments
                    )
                )
            return ModelTurn(assistant=AssistantMessage(content=content), tool_calls=tuple(calls))
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ModelBackendError("Model returned an invalid tool-call response.") from error
