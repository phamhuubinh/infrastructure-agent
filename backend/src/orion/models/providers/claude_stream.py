"""Native Messages block lifecycle; no partial tool arguments authorize dispatch."""

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


class ClaudeStream:
    def __init__(self, names: ToolNameMap) -> None:
        self.names = names
        self.started = self.stopped = False
        self.stop_reason: str | None = None
        self.blocks: dict[int, dict[str, Any]] = {}
        self.open: set[int] = set()
        self.arguments: dict[int, list[str]] = {}
        self.tokens: dict[str, int] = {}

    def _usage(self, value: Any) -> None:
        if not isinstance(value, dict):
            raise ValueError("invalid usage")
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            if key in value:
                count = value[key]
                if type(count) is not int or count < self.tokens.get(key, 0):
                    raise ValueError("invalid cumulative token count")
                self.tokens[key] = count

    def feed(self, frame: SSEEvent) -> tuple[ModelStreamEvent, ...]:
        value = strict_json(frame.data)
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ValueError("invalid native event")
        kind = value["type"]
        if frame.name != kind:
            raise ValueError("native event type mismatch")
        if kind == "error":
            raise ModelBackendError(
                "Claude provider reported an in-stream error.",
                kind=ModelBackendErrorKind.UPSTREAM_STREAM_ERROR,
            )
        if kind == "ping":
            return ()
        known = {
            "message_start",
            "message_delta",
            "message_stop",
            "content_block_start",
            "content_block_delta",
            "content_block_stop",
        }
        if kind not in known:
            return ()  # Forward-compatible metadata events carry no dispatch authority.
        if self.stopped:
            raise ValueError("event after message_stop")
        if kind == "message_start":
            message = value["message"]
            if self.started or message.get("role") != "assistant" or message.get("content") != []:
                raise ValueError("invalid message_start")
            if not isinstance(message.get("id"), str) or not message["id"]:
                raise ValueError("missing message identity")
            self.started = True
            self._usage(message["usage"])
            return ()
        if not self.started:
            raise ValueError("event before message_start")
        if kind == "message_delta":
            if self.open:
                raise ValueError("message_delta before block completion")
            delta = value["delta"]
            if not isinstance(delta, dict):
                raise ValueError("invalid message delta")
            reason = delta.get("stop_reason")
            if reason is not None:
                if reason not in {"end_turn", "stop_sequence", "tool_use"}:
                    raise ModelBackendError(
                        "Claude output ended without a complete usable turn.",
                        kind=ModelBackendErrorKind.INCOMPLETE_STREAM,
                    )
                if self.stop_reason is not None and reason != self.stop_reason:
                    raise ValueError("conflicting stop reasons")
                self.stop_reason = reason
            self._usage(value.get("usage", {}))
            return ()
        if kind == "message_stop":
            if self.open or self.stop_reason is None:
                raise ValueError("premature message_stop")
            self.stopped = True
            return ()
        if self.stop_reason is not None:
            raise ValueError("block after stop reason")
        index = value["index"]
        if type(index) is not int or not 0 <= index < 64:
            raise ValueError("invalid content block index")
        if kind == "content_block_start":
            block = value["content_block"]
            if index in self.blocks or not isinstance(block, dict):
                raise ValueError("duplicate or invalid block")
            block_type = block.get("type")
            if block_type not in {"text", "tool_use", "thinking", "redacted_thinking"}:
                raise ModelBackendError(
                    "Claude returned an unsupported content block.",
                    kind=ModelBackendErrorKind.UNSUPPORTED,
                )
            self.blocks[index] = dict(block)
            self.open.add(index)
            if block_type == "text":
                text = block.get("text")
                if not isinstance(text, str):
                    raise ValueError("invalid text block")
                return (AssistantDelta(content=text),) if text else ()
            if block_type == "tool_use":
                if (
                    not isinstance(block.get("id"), str)
                    or not block["id"]
                    or len(block["id"]) > 256
                    or not isinstance(block.get("name"), str)
                    or not isinstance(block.get("input"), dict)
                ):
                    raise ValueError("invalid tool_use block")
                canonical = self.names.to_canonical(block["name"])
                self.arguments[index] = []
                return (ToolCallDelta(index=index, call_id=block["id"], tool_name=canonical),)
            if block_type == "thinking":
                if not isinstance(block.get("thinking"), str):
                    raise ValueError("invalid thinking block")
                text = block["thinking"]
                return (ReasoningDelta(content=text),) if text else ()
            if not isinstance(block.get("data"), str):
                raise ValueError("invalid redacted thinking block")
            return ()
        if index not in self.open:
            raise ValueError("delta/stop references an unopened block")
        block = self.blocks[index]
        if kind == "content_block_stop":
            if block["type"] == "tool_use" and self.arguments[index]:
                if block["input"]:
                    raise ValueError("mixed initial and fragmented tool input")
                arguments = strict_json("".join(self.arguments[index]))
                if not isinstance(arguments, dict):
                    raise ValueError("tool input is not an object")
                block["input"] = arguments
            if block["type"] == "thinking" and (
                not isinstance(block.get("signature"), str) or not block["signature"]
            ):
                raise ValueError("missing thinking signature")
            self.open.remove(index)
            return ()
        delta = value["delta"]
        delta_type = delta["type"]
        field = {
            "text_delta": "text",
            "thinking_delta": "thinking",
            "signature_delta": "signature",
            "input_json_delta": "partial_json",
        }.get(delta_type)
        expected = {
            "text_delta": "text",
            "thinking_delta": "thinking",
            "signature_delta": "thinking",
            "input_json_delta": "tool_use",
        }.get(delta_type)
        if field is None or expected != block["type"] or not isinstance(delta.get(field), str):
            raise ValueError("invalid block delta")
        text = delta[field]
        if delta_type == "input_json_delta":
            self.arguments[index].append(text)
            return (ToolCallDelta(index=index, arguments_delta=text),)
        block[field] = block.get(field, "") + text
        if delta_type == "text_delta":
            return (AssistantDelta(content=text),) if text else ()
        if delta_type == "thinking_delta":
            return (ReasoningDelta(content=text),) if text else ()
        return ()

    def complete(self) -> tuple[ModelTurn, ModelUsage]:
        if not self.stopped:
            raise ModelBackendError(
                "Claude stream ended before message_stop.",
                kind=ModelBackendErrorKind.INCOMPLETE_STREAM,
            )
        blocks = [self.blocks[index] for index in sorted(self.blocks)]
        if set(self.blocks) != set(range(len(blocks))):
            raise ValueError("noncontiguous block identities")
        calls = tuple(
            ModelToolCall(
                call_id=block["id"],
                tool_name=self.names.to_canonical(block["name"]),
                arguments=block["input"],
            )
            for block in blocks
            if block["type"] == "tool_use"
        )
        if len({call.call_id for call in calls}) != len(calls):
            raise ValueError("duplicate tool identity")
        if (self.stop_reason == "tool_use") != bool(calls):
            raise ValueError("stop reason does not match tool blocks")
        content = "".join(block["text"] for block in blocks if block["type"] == "text")
        if not content and not calls:
            raise ModelBackendError(
                "Claude completed without assistant text or tool calls.",
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
        if "input_tokens" not in self.tokens or "output_tokens" not in self.tokens:
            raise ValueError("missing usage counters")
        usage = ModelUsage(
            input_tokens=sum(
                self.tokens.get(key, 0)
                for key in (
                    "input_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
            ),
            output_tokens=self.tokens["output_tokens"],
        )
        return ModelTurn(assistant=assistant, tool_calls=calls), usage
