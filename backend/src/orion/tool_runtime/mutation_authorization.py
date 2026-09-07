"""Trusted bootstrap policy for exact infrastructure mutation authorization."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from orion.contracts import RuntimeScope, ToolDefinition


class MutationAuthorizationConfigurationError(ValueError):
    """A server-side mutation policy cannot be interpreted safely."""


@dataclass(frozen=True)
class MutationAuthorizationPolicy:
    """Allow only exact configured mutation operation/target pairs."""

    allowed_pairs: frozenset[tuple[str, str]] = frozenset()

    @classmethod
    def read_only(cls) -> MutationAuthorizationPolicy:
        return cls()

    @classmethod
    def from_mapping(
        cls,
        raw: dict[str, object],
        definitions: Iterable[ToolDefinition],
        target_is_configured: Callable[[str, str], bool],
    ) -> MutationAuthorizationPolicy:
        """Validate the policy against the same bootstrap registry and target snapshot."""
        if "mutation_allowlist" not in raw:
            return cls.read_only()
        entries = raw["mutation_allowlist"]
        if not isinstance(entries, list):
            raise MutationAuthorizationConfigurationError(
                "mutation_allowlist must be an array of exact operation and target entries."
            )

        definitions_by_name = {definition.name: definition for definition in definitions}
        allowed: set[tuple[str, str]] = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"tool_name", "target_ref"}:
                raise MutationAuthorizationConfigurationError(
                    "Each mutation allowlist entry must contain only tool_name and target_ref."
                )
            tool_name, target_ref = entry["tool_name"], entry["target_ref"]
            if not isinstance(tool_name, str) or not isinstance(target_ref, str):
                raise MutationAuthorizationConfigurationError(
                    "Mutation allowlist entries require string tool_name and target_ref values."
                )
            definition = definitions_by_name.get(tool_name)
            if definition is None or definition.operation_kind != "mutation":
                raise MutationAuthorizationConfigurationError(
                    "Mutation allowlist names one unknown or non-mutation tool."
                )
            schema = definition.input_schema
            if (
                schema.get("additionalProperties") is not False
                or "target_ref" not in schema.get("required", ())
                or schema.get("properties", {}).get("target_ref", {}).get("type") != "string"
            ):
                raise MutationAuthorizationConfigurationError(
                    "Mutation allowlist requires a closed schema with a required target_ref."
                )
            family = tool_name.partition(".")[0]
            if family not in {"linux", "grafana", "zabbix"} or not target_is_configured(
                family, target_ref
            ):
                raise MutationAuthorizationConfigurationError(
                    "Mutation allowlist names an unknown configured target."
                )
            pair = (tool_name, target_ref)
            if pair in allowed:
                raise MutationAuthorizationConfigurationError(
                    "Mutation allowlist contains a duplicate operation and target entry."
                )
            allowed.add(pair)
        return cls(frozenset(allowed))

    def authorizes(
        self, definition: ToolDefinition, arguments: dict[str, object], scope: RuntimeScope
    ) -> bool:
        """Return whether this policy authorizes a validated mutation call."""
        del scope
        if definition.operation_kind != "mutation":
            return True
        target_ref = arguments.get("target_ref")
        return isinstance(target_ref, str) and (definition.name, target_ref) in self.allowed_pairs
