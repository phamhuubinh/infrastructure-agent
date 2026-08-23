"""Canonical capability metadata and exact registry for Orion."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from src.agent.permissions import EffectClass

_MAX_ID_CHARS = 128
_MAX_TEXT_CHARS = 1024
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")

_ALLOWED_SCHEMA_KEYS = frozenset(
    {
        "type",
        "additionalProperties",
        "properties",
        "required",
        "enum",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "items",
    }
)

_ALLOWED_JSON_TYPES = frozenset(
    {
        "null",
        "string",
        "boolean",
        "integer",
        "number",
        "array",
        "object",
    }
)


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    capability_id: str
    purpose: str
    tool_id: str
    effect: EffectClass
    arguments_schema: Mapping[str, object]
    runtime_binding: str
    discovery_group: str | None = None
    target_kind: str | None = None
    source_kind: str | None = None
    allowed_target_refs: frozenset[str] | None = None
    allowed_source_refs: frozenset[str] | None = None
    available: bool = True
    safety_reviewed: bool = True
    budget_cost: int = 1
    result_kind: str = "observation"
    activity_label: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.capability_id, "capability_id")
        _require_text(self.purpose, "purpose", _MAX_TEXT_CHARS)
        _require_identifier(self.tool_id, "tool_id")
        _require_identifier(self.runtime_binding, "runtime_binding")

        if not isinstance(self.effect, EffectClass):
            raise TypeError("effect must be EffectClass.")

        for field_name in ("target_kind", "source_kind"):
            value = getattr(self, field_name)
            if value is not None:
                _require_identifier(value, field_name)

        for field_name, kind_field in (
            ("allowed_target_refs", "target_kind"),
            ("allowed_source_refs", "source_kind"),
        ):
            value = getattr(self, field_name)

            if value is None:
                continue

            if getattr(self, kind_field) is None:
                raise ValueError(
                    f"{field_name} requires {kind_field}."
                )

            if not isinstance(value, frozenset) or any(
                not isinstance(item, str) or not item
                for item in value
            ):
                raise TypeError(
                    f"{field_name} must be frozenset[str] or None."
                )

        if type(self.available) is not bool:
            raise TypeError("available must be bool.")

        if type(self.safety_reviewed) is not bool:
            raise TypeError("safety_reviewed must be bool.")

        if type(self.budget_cost) is not int or self.budget_cost < 1:
            raise ValueError("budget_cost must be a positive integer.")

        _require_identifier(self.result_kind, "result_kind")

        if self.activity_label is not None:
            _require_text(
                self.activity_label,
                "activity_label",
                _MAX_TEXT_CHARS,
            )

        if (
            not isinstance(self.arguments_schema, Mapping)
            or self.arguments_schema.get("type") != "object"
            or self.arguments_schema.get("additionalProperties") is not False
        ):
            raise ValueError(
                "arguments_schema must be a closed object schema "
                "with additionalProperties=false."
            )

        _validate_schema_definition(
            self.arguments_schema,
            path="arguments",
        )

        object.__setattr__(
            self,
            "arguments_schema",
            _freeze_json(self.arguments_schema),
        )


class CapabilityRegistry:
    """Exact, immutable capability lookup. No aliases or semantic fallback."""

    def __init__(
        self,
        capabilities: Sequence[CapabilityDefinition],
    ) -> None:
        if any(
            not isinstance(item, CapabilityDefinition)
            for item in capabilities
        ):
            raise TypeError(
                "capabilities must contain CapabilityDefinition values."
            )

        ids = [item.capability_id for item in capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("Capability IDs must be unique.")

        self._capabilities = tuple(capabilities)
        self._by_id = {
            item.capability_id: item
            for item in capabilities
        }

    @property
    def capabilities(self) -> tuple[CapabilityDefinition, ...]:
        return self._capabilities

    def get(
        self,
        capability_id: str,
    ) -> CapabilityDefinition | None:
        if not isinstance(capability_id, str):
            raise TypeError("capability_id must be a string.")
        return self._by_id.get(capability_id)


def thaw_schema(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: thaw_schema(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [thaw_schema(item) for item in value]

    return value


def _require_identifier(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_ID_CHARS
        or _ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(f"{field_name} must be a stable identifier.")
    return value


def _require_text(
    value: object,
    field_name: str,
    max_chars: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > max_chars
    ):
        raise ValueError(
            f"{field_name} must be bounded non-empty trimmed text."
        )
    return value


def _schema_types(
    schema: Mapping[str, object],
    *,
    path: str,
) -> tuple[str, ...]:
    raw = schema.get("type")

    if isinstance(raw, str):
        types = (raw,)
    elif (
        isinstance(raw, Sequence)
        and not isinstance(raw, (str, bytes))
        and raw
        and all(isinstance(item, str) for item in raw)
    ):
        types = tuple(raw)
    else:
        raise ValueError(f"{path}.type must declare JSON type(s).")

    if len(types) != len(set(types)):
        raise ValueError(f"{path}.type contains duplicates.")

    if any(item not in _ALLOWED_JSON_TYPES for item in types):
        raise ValueError(f"{path}.type contains unsupported JSON type.")

    return types


def _validate_schema_definition(
    schema: object,
    *,
    path: str,
) -> None:
    if not isinstance(schema, Mapping):
        raise ValueError(f"{path} schema must be an object.")

    unknown = set(schema) - _ALLOWED_SCHEMA_KEYS
    if unknown:
        raise ValueError(
            f"{path} schema contains unsupported keywords: "
            f"{sorted(unknown)}."
        )

    types = _schema_types(schema, path=path)

    if "object" in types:
        if schema.get("additionalProperties") is not False:
            raise ValueError(
                f"{path} object schema must set "
                "additionalProperties=false."
            )

        properties = schema.get("properties")
        required = schema.get("required", [])

        if not isinstance(properties, Mapping):
            raise ValueError(
                f"{path}.properties must be an object."
            )

        if (
            not isinstance(required, Sequence)
            or isinstance(required, (str, bytes))
            or any(not isinstance(item, str) for item in required)
        ):
            raise ValueError(
                f"{path}.required must be an array of strings."
            )

        if len(required) != len(set(required)):
            raise ValueError(
                f"{path}.required contains duplicates."
            )

        undeclared = set(required) - set(properties)
        if undeclared:
            raise ValueError(
                f"{path}.required references undeclared properties."
            )

        for name, child in properties.items():
            if not isinstance(name, str) or not name:
                raise ValueError(
                    f"{path}.properties keys must be non-empty strings."
                )
            _validate_schema_definition(
                child,
                path=f"{path}.{name}",
            )

    elif any(
        key in schema
        for key in (
            "additionalProperties",
            "properties",
            "required",
        )
    ):
        raise ValueError(
            f"{path} uses object keywords without object type."
        )

    if "array" in types:
        items = schema.get("items")
        if items is not None:
            _validate_schema_definition(
                items,
                path=f"{path}[]",
            )
    elif any(
        key in schema
        for key in ("items", "minItems", "maxItems")
    ):
        raise ValueError(
            f"{path} uses array keywords without array type."
        )

    enum = schema.get("enum")
    if enum is not None and (
        not isinstance(enum, Sequence)
        or isinstance(enum, (str, bytes))
        or not enum
    ):
        raise ValueError(f"{path}.enum must be a non-empty array.")

    for key in ("minimum", "maximum"):
        value = schema.get(key)
        if value is not None and (
            type(value) not in {int, float}
        ):
            raise ValueError(f"{path}.{key} must be numeric.")

    for key in (
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
    ):
        value = schema.get(key)
        if value is not None and (
            type(value) is not int or value < 0
        ):
            raise ValueError(
                f"{path}.{key} must be a non-negative integer."
            )

    pattern = schema.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise ValueError(f"{path}.pattern must be a string.")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"{path}.pattern must be valid regex."
            ) from exc


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze_json(item)
                for key, item in value.items()
            }
        )

    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
    ):
        return tuple(_freeze_json(item) for item in value)

    return value
