"""Shared Chat Completions decoding, independent of vendor request/state policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from orion.contracts import (
    AssistantDelta,
    AssistantMessage,
    ModelToolCall,
    ModelTurn,
    ModelUsage,
    ReasoningDelta,
    ToolCallDelta,
    citation_source_ref_ids_from_content,
)
from orion.models.backend import ModelBackendError, ModelBackendErrorKind
from orion.models.providers.transport import strict_json


@dataclass
class PendingToolCall:
    call_id: str = ""
    tool_name: str = ""
    arguments: str = ""


class ChatCompletionsDecoder:
    @staticmethod
    def _parse_chunk(raw_chunk: str) -> dict[str, Any]:
        chunk = strict_json(raw_chunk)
        if not isinstance(chunk, dict):
            raise ValueError("provider stream chunk is not an object")
        return chunk

    @staticmethod
    def _raise_for_stream_error(chunk: dict[str, Any]) -> None:
        if chunk.get("error") is not None or chunk.get("object") == "error":
            raise ModelBackendError(
                "Chat-completions provider reported an in-stream error.",
                kind=ModelBackendErrorKind.UPSTREAM_STREAM_ERROR,
            )

    @staticmethod
    def _chunk_has_finish_reason(chunk: dict[str, Any]) -> bool:
        choices = chunk.get("choices", [])
        if not isinstance(choices, list):
            raise ValueError("provider stream choices are not a list")
        if not choices:
            return False
        if len(choices) != 1:
            raise ValueError("multiple provider choices are unsupported")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ValueError("provider stream choice is not an object")
        finish_reason = choice.get("finish_reason")
        if finish_reason is None:
            return False
        if not isinstance(finish_reason, str):
            raise ValueError("provider stream finish reason is invalid")
        if finish_reason not in {"stop", "tool_calls", "function_call"}:
            raise ModelBackendError(
                "Model output was truncated, filtered or ended with an unsupported reason.",
                kind=ModelBackendErrorKind.INCOMPLETE_STREAM,
            )
        return True

    def _normalize_chunk(
        self,
        chunk: dict[str, Any],
        content_parts: list[str],
        calls: dict[int, PendingToolCall],
    ) -> tuple[AssistantDelta | ReasoningDelta | ToolCallDelta, ...]:
        try:
            choices = chunk.get("choices", [])
            if not choices:
                return ()
            delta = choices[0].get("delta", {})
            if not isinstance(delta, dict):
                raise ValueError("provider stream delta is not an object")
            events: list[AssistantDelta | ReasoningDelta | ToolCallDelta] = []
            for field_name in ("reasoning", "reasoning_content"):
                reasoning = delta.get(field_name)
                if reasoning is not None:
                    if not isinstance(reasoning, str):
                        raise ValueError("reasoning delta is not a string")
                    if reasoning:
                        events.append(ReasoningDelta(content=reasoning))
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
                if type(index) is not int or not 0 <= index < 64:
                    raise ValueError("tool call delta index is invalid")
                pending = calls.setdefault(index, PendingToolCall())
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
                if (
                    len(pending.call_id) > 256
                    or len(pending.tool_name) > 256
                    or len(pending.arguments.encode("utf-8")) > 262_144
                ):
                    raise ValueError("tool call exceeds protocol bounds")
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
            raise ModelBackendError(
                "Chat-completions model stream was malformed.",
                kind=ModelBackendErrorKind.MALFORMED_STREAM,
            ) from error

    @staticmethod
    def _usage_from_chunk(chunk: dict[str, Any]) -> ModelUsage | None:
        raw_usage = chunk.get("usage")
        if raw_usage is None:
            return None
        if not isinstance(raw_usage, dict):
            raise ValueError("provider usage is not an object")
        input_tokens = raw_usage.get("prompt_tokens")
        output_tokens = raw_usage.get("completion_tokens")
        if (
            type(input_tokens) is not int
            or input_tokens < 0
            or type(output_tokens) is not int
            or output_tokens < 0
        ):
            raise ValueError("provider usage is invalid")
        return ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens)

    @staticmethod
    def _build_turn(content_parts: list[str], calls: dict[int, PendingToolCall]) -> ModelTurn:
        try:
            tool_calls: list[ModelToolCall] = []
            call_ids: set[str] = set()
            for index in sorted(calls):
                pending = calls[index]
                if not pending.call_id or not pending.tool_name:
                    raise ValueError("streamed tool call is incomplete")
                if pending.call_id in call_ids:
                    raise ValueError("streamed tool call ID is duplicated")
                call_ids.add(pending.call_id)
                arguments = strict_json(pending.arguments)
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
            if not content and not tool_calls:
                raise ModelBackendError(
                    "Chat-completions model completed without assistant content or tool calls.",
                    kind=ModelBackendErrorKind.EMPTY_TURN,
                )
            citation_refs = citation_source_ref_ids_from_content(content)
            assistant = None
            if content:
                assistant = AssistantMessage(
                    content=content,
                    citation_evidence_refs=citation_refs,
                )
            return ModelTurn(assistant=assistant, tool_calls=tuple(tool_calls))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ModelBackendError(
                "Chat-completions model stream was malformed.",
                kind=ModelBackendErrorKind.MALFORMED_STREAM,
            ) from error
