"""Bounded, conservative MCP JSON Schema adaptation for canonical Orion tools."""

from __future__ import annotations

import json
import re
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from orion.integrations.mcp.config import MCPConfigurationError

MAX_SCHEMA_BYTES = 32 * 1024
AUTHORITY_FIELDS = frozenset(
    {
        "principal_id",
        "workspace_id",
        "project_id",
        "session_id",
        "mutation_mode",
        "runtime_scope",
        "attachment_ids",
        "mutation_allowlist",
        "operation_kind",
        "authorization",
    }
)
_ALLOWED = {
    "type",
    "title",
    "description",
    "default",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "uniqueItems",
}
_TYPES = {"string", "integer", "number", "boolean", "object", "array", "null"}


def adapt_schema(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        if len(json.dumps(raw, allow_nan=False).encode()) > MAX_SCHEMA_BYTES:
            raise ValueError("oversized schema")
        Draft202012Validator.check_schema(raw)
        result = _adapt(raw, 0)
        if result.get("type") != "object":
            raise ValueError("tool must accept an object")
        Draft202012Validator.check_schema(result)
        return result
    except (ValueError, TypeError, SchemaError, RecursionError):
        raise MCPConfigurationError("schema") from None


def _adapt(raw: Any, depth: int) -> dict[str, Any]:
    if depth > 8 or not isinstance(raw, dict) or set(raw) - _ALLOWED:
        raise ValueError("unsupported schema")
    kind = raw.get("type")
    if not isinstance(kind, str) or kind not in _TYPES:
        raise ValueError("ambiguous type")
    result = dict(raw)
    result.pop("title", None)
    result.pop("default", None)
    if "description" in raw and (
        not isinstance(raw["description"], str) or len(raw["description"]) > 2048
    ):
        raise ValueError("invalid description")
    if kind == "object":
        properties = raw.get("properties", {})
        if (
            not isinstance(properties, dict)
            or len(properties) > 64
            or raw.get("additionalProperties", False) is not False
        ):
            raise ValueError("open object")
        for key in properties:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key) or (
                key.lower() in AUTHORITY_FIELDS
            ):
                raise ValueError("unsafe property")
        required = raw.get("required", [])
        if not isinstance(required, list) or set(required) - set(properties):
            raise ValueError("invalid required")
        result["properties"] = {key: _adapt(value, depth + 1) for key, value in properties.items()}
        result["required"] = list(required)
        result["additionalProperties"] = False
    elif kind == "array":
        result["items"] = _adapt(raw.get("items"), depth + 1)
    elif set(raw) & {"properties", "required", "additionalProperties", "items"}:
        raise ValueError("ambiguous structure")
    return result


def validate_output_schema(raw: dict[str, Any]) -> None:
    """Output is untrusted data; bound SDK validation and forbid reference resolution."""

    def visit(value: Any, depth: int) -> None:
        if depth > 16:
            raise ValueError("deep output schema")
        if isinstance(value, dict):
            if set(value) & {"$ref", "$dynamicRef", "$recursiveRef"}:
                raise ValueError("output reference")
            for child in value.values():
                visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth + 1)

    try:
        if len(json.dumps(raw, allow_nan=False).encode()) > MAX_SCHEMA_BYTES:
            raise ValueError("oversized output schema")
        Draft202012Validator.check_schema(raw)
        visit(raw, 0)
    except (ValueError, TypeError, SchemaError, RecursionError):
        raise MCPConfigurationError("schema") from None
