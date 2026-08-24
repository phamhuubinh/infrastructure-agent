"""The one authoritative model-visible tool registry."""

from __future__ import annotations

from collections.abc import Callable

from orion.contracts import ToolCall, ToolDefinition, ToolResult

ToolHandler = Callable[[ToolCall], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"duplicate tool name: {definition.name}")
        if definition.handler_key in self._handlers:
            raise ValueError(f"duplicate handler key: {definition.handler_key}")
        self._definitions[definition.name] = definition
        self._handlers[definition.handler_key] = handler

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions.values())

    def definition(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def handler(self, handler_key: str) -> ToolHandler | None:
        return self._handlers.get(handler_key)
