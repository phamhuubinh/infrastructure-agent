"""The one authoritative immutable model-visible tool registry."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from jsonschema import SchemaError
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for

from orion.contracts import ToolCall, ToolDefinition, freeze_json
from orion.security import redact_public

ToolHandler = Callable[[ToolCall], object]


@dataclass(frozen=True)
class ToolRegistration:
    definition: ToolDefinition
    handler: ToolHandler


class ToolRegistryBuilder:
    """Bootstrap-only mutable registry construction with eager validation."""

    def __init__(self) -> None:
        self._registrations: list[ToolRegistration] = []
        self._names: set[str] = set()
        self._handler_keys: set[str] = set()

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        if definition.name in self._names:
            raise ValueError(f"duplicate tool name: {definition.name}")
        if definition.handler_key in self._handler_keys:
            raise ValueError(f"duplicate handler key: {definition.handler_key}")
        try:
            validator_for(definition.input_schema).check_schema(definition.input_schema)
        except SchemaError as error:
            raise ValueError(f"invalid JSON Schema for tool {definition.name}") from error
        self._names.add(definition.name)
        self._handler_keys.add(definition.handler_key)
        self._registrations.append(ToolRegistration(definition=definition, handler=handler))

    def freeze(self) -> ToolRegistry:
        return ToolRegistry(self._registrations)


class ToolRegistry:
    """Immutable bootstrap snapshot used by every model turn in the application."""

    def __init__(self, registrations: Iterable[ToolRegistration]) -> None:
        definitions: dict[str, ToolDefinition] = {}
        handlers: dict[str, ToolHandler] = {}
        validators: dict[str, Validator] = {}
        for registration in registrations:
            definition = ToolDefinition.model_validate(registration.definition.model_dump())
            object.__setattr__(definition, "input_schema", freeze_json(definition.input_schema))
            if definition.name in definitions:
                raise ValueError(f"duplicate tool name: {definition.name}")
            if definition.handler_key in handlers:
                raise ValueError(f"duplicate handler key: {definition.handler_key}")
            try:
                validator_class = validator_for(definition.input_schema)
                validator_class.check_schema(definition.input_schema)
            except SchemaError as error:
                raise ValueError(f"invalid JSON Schema for tool {definition.name}") from error
            definitions[definition.name] = definition
            handlers[definition.handler_key] = registration.handler
            validators[definition.name] = validator_class(definition.input_schema)
        self._definitions: Mapping[str, ToolDefinition] = MappingProxyType(definitions)
        self._handlers: Mapping[str, ToolHandler] = MappingProxyType(handlers)
        self._validators: Mapping[str, Validator] = MappingProxyType(validators)
        # The registry and its definitions are immutable after bootstrap. Sanitize
        # and validate the provider snapshot once instead of rebuilding 25 nested
        # schema models on every initial and resumed model turn.
        model_definitions: list[ToolDefinition] = []
        for name in sorted(definitions):
            definition = ToolDefinition.model_validate(
                redact_public(definitions[name].model_dump())
            )
            object.__setattr__(definition, "input_schema", freeze_json(definition.input_schema))
            model_definitions.append(definition)
        self._model_definitions = tuple(model_definitions)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        # Definitions cross the model boundary. Internal handler bindings remain in
        # the immutable registry, but descriptions/schema annotations are sanitized.
        # Preserve the public method's isolation from nested-dict mutation.
        return tuple(
            ToolDefinition.model_validate(definition.model_dump())
            for definition in self._model_definitions
        )

    def model_definitions(self) -> tuple[ToolDefinition, ...]:
        """Return the trusted immutable snapshot for the ChatRuntime/provider path."""
        return self._model_definitions

    def definition(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def handler(self, handler_key: str) -> ToolHandler | None:
        return self._handlers.get(handler_key)

    def arguments_are_valid(self, tool_name: str, arguments: object) -> bool:
        validator = self._validators.get(tool_name)
        return validator is not None and not any(validator.iter_errors(cast(Any, arguments)))
