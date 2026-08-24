"""The one authoritative model-visible tool registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jsonschema import SchemaError
from jsonschema.validators import validator_for

from orion.contracts import ToolCall, ToolDefinition

ToolHandler = Callable[[ToolCall], object]


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._validators: dict[str, Any] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"duplicate tool name: {definition.name}")
        if definition.handler_key in self._handlers:
            raise ValueError(f"duplicate handler key: {definition.handler_key}")
        try:
            validator_class = validator_for(definition.input_schema)
            validator_class.check_schema(definition.input_schema)
            validator = validator_class(definition.input_schema)
        except SchemaError as error:
            raise ValueError(f"invalid JSON Schema for tool {definition.name}") from error
        self._definitions[definition.name] = definition
        self._handlers[definition.handler_key] = handler
        self._validators[definition.name] = validator

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions.values())

    def definition(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def handler(self, handler_key: str) -> ToolHandler | None:
        return self._handlers.get(handler_key)

    def arguments_are_valid(self, tool_name: str, arguments: object) -> bool:
        validator = self._validators.get(tool_name)
        return validator is not None and not any(validator.iter_errors(arguments))
