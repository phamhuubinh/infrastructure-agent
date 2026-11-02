"""Native Responses item/event reconstruction, independent of Chat Completions."""

from __future__ import annotations

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
from orion.models.backend import ModelBackendError, ModelBackendErrorKind, ModelStreamEvent
from orion.models.providers.tool_names import ToolNameMap
from orion.models.providers.transport import SSEEvent, strict_json


class ResponsesStream:
    def __init__(self, names: ToolNameMap) -> None:
        self.names = names
        self.response_id: str | None = None
        self.sequence = -1
        self.items: dict[int, dict[str, Any]] = {}
        self.finished: dict[int, dict[str, Any]] = {}
        self.arguments: dict[int, str] = {}
        self.arguments_done: set[int] = set()
        self.parts: dict[tuple[int, int], dict[str, Any]] = {}
        self.text_done: set[tuple[int, int]] = set()
        self.parts_done: set[tuple[int, int]] = set()
        self.response: dict[str, Any] | None = None

    @staticmethod
    def _index(value: Any) -> int:
        if type(value) is not int or not 0 <= value < 64:
            raise ValueError("invalid native index")
        return value

    def _item(self, value: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        index = self._index(value["output_index"])
        item = self.items[index]
        if index in self.finished or value.get("item_id") != item["id"]:
            raise ValueError("event references wrong or closed item")
        return index, item

    @staticmethod
    def _same_item(first: dict[str, Any], second: dict[str, Any]) -> bool:
        keys = {
            "function_call": ("id", "type", "call_id", "name", "arguments"),
            "message": ("id", "type", "role", "content"),
            "reasoning": ("id", "type", "summary", "encrypted_content"),
        }.get(str(first.get("type")), ())
        return bool(keys) and all(first.get(key) == second.get(key) for key in keys)

    def feed(self, frame: SSEEvent) -> tuple[ModelStreamEvent, ...]:
        value = strict_json(frame.data)
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ValueError("invalid native event")
        kind = value["type"]
        if frame.name not in {"message", kind}:
            raise ValueError("native event type mismatch")
        if "sequence_number" in value:
            sequence = value["sequence_number"]
            if type(sequence) is not int or sequence <= self.sequence:
                raise ValueError("native event sequence is invalid")
            self.sequence = sequence
        if kind == "error" or kind == "response.failed":
            raise ModelBackendError(
                "OpenAI provider reported a response error.",
                kind=ModelBackendErrorKind.UPSTREAM_STREAM_ERROR,
            )
        if kind == "response.incomplete":
            raise ModelBackendError(
                "OpenAI response is incomplete.", kind=ModelBackendErrorKind.INCOMPLETE_STREAM
            )
        if self.response is not None:
            raise ValueError("event after response completion")
        if kind == "response.created":
            response = value["response"]
            if self.response_id is not None or not isinstance(response.get("id"), str):
                raise ValueError("duplicate or invalid response identity")
            if not response["id"] or response.get("status") not in {"queued", "in_progress"}:
                raise ValueError("invalid created response")
            self.response_id = response["id"]
            return ()
        if self.response_id is None:
            raise ValueError("event before response.created")
        if "response_id" in value and value["response_id"] != self.response_id:
            raise ValueError("response identity mismatch")
        if kind == "response.in_progress":
            if value["response"]["id"] != self.response_id:
                raise ValueError("response identity mismatch")
            return ()
        if kind == "response.output_item.added":
            index = self._index(value["output_index"])
            item = value["item"]
            if index in self.items or not isinstance(item, dict):
                raise ValueError("duplicate or invalid output item")
            item_type = item.get("type")
            if item_type not in {"message", "function_call", "reasoning"}:
                raise ModelBackendError(
                    "OpenAI returned an unsupported output item.",
                    kind=ModelBackendErrorKind.UNSUPPORTED,
                )
            if (
                not isinstance(item.get("id"), str)
                or not item["id"]
                or any(previous["id"] == item["id"] for previous in self.items.values())
            ):
                raise ValueError("invalid output item identity")
            self.items[index] = dict(item)
            if item_type == "function_call":
                if (
                    not isinstance(item.get("call_id"), str)
                    or not item["call_id"]
                    or len(item["call_id"]) > 256
                    or not isinstance(item.get("name"), str)
                    or not isinstance(item.get("arguments"), str)
                ):
                    raise ValueError("invalid function item")
                self.arguments[index] = item["arguments"]
                return (
                    ToolCallDelta(
                        index=index,
                        call_id=item["call_id"],
                        tool_name=self.names.to_canonical(item["name"]),
                    ),
                )
            if item_type == "message" and (
                item.get("role") != "assistant" or item.get("content") != []
            ):
                raise ValueError("invalid assistant output item")
            return ()
        if kind == "response.completed":
            response = value["response"]
            if response.get("id") != self.response_id or response.get("status") != "completed":
                raise ValueError("invalid completed response")
            if response.get("error") is not None or response.get("incomplete_details") is not None:
                raise ValueError("completed response contains failure metadata")
            output = response.get("output")
            if (
                not isinstance(output, list)
                or len(output) != len(self.items)
                or set(self.finished) != set(range(len(output)))
            ):
                raise ValueError("response completed with unfinished items")
            if not all(
                isinstance(item, dict) and self._same_item(self.finished[index], item)
                for index, item in enumerate(output)
            ):
                raise ValueError("completed response contradicts streamed items")
            self.response = response
            return ()
        if kind == "response.output_item.done":
            index = self._index(value["output_index"])
            item, original = value["item"], self.items[index]
            if (
                index in self.finished
                or not isinstance(item, dict)
                or item.get("id") != original["id"]
                or item.get("type") != original["type"]
            ):
                raise ValueError("invalid completed item identity")
            if item["type"] == "function_call":
                if (
                    index not in self.arguments_done
                    or item.get("arguments") != self.arguments[index]
                    or item.get("name") != original["name"]
                    or item.get("call_id") != original["call_id"]
                ):
                    raise ValueError("function completion contradicts deltas")
            elif item["type"] == "message":
                content = item.get("content")
                if not isinstance(content, list):
                    raise ValueError("invalid final message content")
                expected = [self.parts[(index, part)] for part in range(len(content))]
                if (
                    content != expected
                    or {part for output, part in self.parts if output == index}
                    != set(range(len(content)))
                    or any((index, part) not in self.parts_done for part in range(len(content)))
                    or item.get("role") != "assistant"
                ):
                    raise ValueError("message completion contradicts content parts")
            self.finished[index] = item
            if item.get("status") not in {None, "completed"}:
                raise ValueError("output item has not completed")
            return ()
        if kind == "response.content_part.added":
            index, item = self._item(value)
            part_index = self._index(value["content_index"])
            key = (index, part_index)
            part = value["part"]
            if item["type"] != "message" or key in self.parts or not isinstance(part, dict):
                raise ValueError("invalid content part")
            if part.get("type") not in {"output_text", "refusal"}:
                raise ModelBackendError(
                    "OpenAI returned an unsupported content part.",
                    kind=ModelBackendErrorKind.UNSUPPORTED,
                )
            field = "text" if part["type"] == "output_text" else "refusal"
            if not isinstance(part.get(field), str):
                raise ValueError("invalid initial text")
            self.parts[key] = dict(part)
            return (AssistantDelta(content=part[field]),) if part[field] else ()
        if kind in {
            "response.output_text.delta",
            "response.refusal.delta",
            "response.output_text.done",
            "response.refusal.done",
            "response.content_part.done",
        }:
            index, item = self._item(value)
            key = (index, self._index(value["content_index"]))
            part = self.parts[key]
            if item["type"] != "message" or key in self.parts_done:
                raise ValueError("content event references closed/wrong item")
            field = "text" if part["type"] == "output_text" else "refusal"
            if kind == "response.content_part.done":
                final = value["part"]
                if (
                    key not in self.text_done
                    or final.get("type") != part["type"]
                    or final.get(field) != part[field]
                ):
                    raise ValueError("content part completion contradicts text")
                self.parts[key] = final
                self.parts_done.add(key)
                return ()
            if ("refusal" in kind) != (part["type"] == "refusal"):
                raise ValueError("text event type mismatch")
            if key in self.text_done:
                raise ValueError("text after completion")
            if kind.endswith(".done"):
                if value.get(field) != part[field]:
                    raise ValueError("text completion contradicts deltas")
                self.text_done.add(key)
                return ()
            delta = value["delta"]
            if not isinstance(delta, str):
                raise ValueError("invalid text delta")
            part[field] += delta
            return (AssistantDelta(content=delta),) if delta else ()
        if kind in {
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
        }:
            index, item = self._item(value)
            if item["type"] != "function_call" or index in self.arguments_done:
                raise ValueError("arguments reference a closed/wrong function")
            if kind.endswith(".done"):
                if value.get("arguments") != self.arguments[index]:
                    raise ValueError("argument completion contradicts deltas")
                self.arguments_done.add(index)
                return ()
            delta = value["delta"]
            if not isinstance(delta, str):
                raise ValueError("invalid argument delta")
            self.arguments[index] += delta
            if len(self.arguments[index].encode()) > 262_144:
                raise ValueError("tool arguments exceed protocol bounds")
            return (ToolCallDelta(index=index, arguments_delta=delta),)
        if kind in {"response.reasoning_summary_text.delta", "response.reasoning_text.delta"}:
            _, item = self._item(value)
            if item["type"] != "reasoning" or not isinstance(value.get("delta"), str):
                raise ValueError("invalid private reasoning delta")
            return (ReasoningDelta(content=value["delta"]),) if value["delta"] else ()
        return ()  # Future metadata cannot create tools or a completed turn.

    def complete(self) -> tuple[ModelTurn, ModelUsage]:
        if self.response is None:
            raise ModelBackendError(
                "OpenAI stream ended before response.completed.",
                kind=ModelBackendErrorKind.INCOMPLETE_STREAM,
            )
        calls: list[ModelToolCall] = []
        text: list[str] = []
        for item in self.response["output"]:
            if item["type"] == "function_call":
                arguments = strict_json(item["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError("function arguments must be an object")
                calls.append(
                    ModelToolCall(
                        call_id=item["call_id"],
                        tool_name=self.names.to_canonical(item["name"]),
                        arguments=arguments,
                    )
                )
            elif item["type"] == "message":
                text.extend(
                    part["text"] if part["type"] == "output_text" else part["refusal"]
                    for part in item["content"]
                )
            elif (
                not isinstance(item.get("encrypted_content"), str) or not item["encrypted_content"]
            ):
                raise ValueError("stateless reasoning requires encrypted continuation")
        if len({call.call_id for call in calls}) != len(calls):
            raise ValueError("duplicate function call identity")
        content = "".join(text)
        if not content and not calls:
            raise ModelBackendError(
                "OpenAI completed without assistant text or function calls.",
                kind=ModelBackendErrorKind.EMPTY_TURN,
            )
        assistant = (
            AssistantMessage(
                content=content,
                citation_evidence_refs=citation_source_ref_ids_from_content(content),
            )
            if content
            else None
        )
        usage = self.response["usage"]
        if (
            not isinstance(usage, dict)
            or type(usage.get("input_tokens")) is not int
            or type(usage.get("output_tokens")) is not int
            or usage["input_tokens"] < 0
            or usage["output_tokens"] < 0
        ):
            raise ValueError("invalid usage")
        return ModelTurn(assistant=assistant, tool_calls=tuple(calls)), ModelUsage(
            input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"]
        )
