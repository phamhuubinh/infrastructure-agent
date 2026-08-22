"""Fail-closed authorization for one model-selected Agent v2 action.

The validator is deliberately metadata-only.  It has no execution, provider,
natural-language, or capability-selection dependency: an action is executable
only after this module returns :class:`AgentActionValidationStatus.VALID`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from src.agent.controller_contracts import AgentAction
from src.pipeline.basic_calculator import CalculatorRequest
from src.pipeline.calculator_action_contract import (
    CALCULATOR_CAPABILITY_ID,
    CalculatorActionBindingError,
    bind_calculator_action,
)
from src.pipeline.controller_capability_discovery import (
    CapabilityDetailStatus,
    ControllerCapabilityDiscovery,
    SelectedCapabilityDetailResult,
)
from src.pipeline.hard_request_constraints import (
    HardRequestConstraints,
    HardTargetReference,
)
from src.pipeline.internet_action_contract import (
    INTERNET_CURRENT_CAPABILITY_ID,
    INTERNET_FETCH_URL_CAPABILITY_ID,
    InternetActionBindingError,
    InternetActionRequest,
    bind_internet_action,
)
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.security.parameter_safety_inspector import ParameterSafetyInspector
from src.pipeline.security.read_only_inspector import ReadOnlyInspector
from src.pipeline.security.tool_inspector import InspectionContext
from src.pipeline.target_resolver import TargetResolver


class AgentActionValidationStatus(str, Enum):
    VALID = "valid"
    CLARIFY = "clarify"
    UNAVAILABLE = "unavailable"
    REJECT = "reject"


class AgentActionValidationReason(str, Enum):
    CAPABILITY_UNKNOWN = "capability_unknown"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    SOURCE_FORBIDDEN = "source_forbidden"
    TARGET_REQUIRED = "target_required"
    TARGET_UNKNOWN = "target_unknown"
    TARGET_MISMATCH = "target_mismatch"
    ARGUMENT_REQUIRED = "argument_required"
    ARGUMENT_UNDECLARED = "argument_undeclared"
    ARGUMENT_INVALID = "argument_invalid"
    ARGUMENT_UNSAFE = "argument_unsafe"
    URL_INVALID = "url_invalid"
    CAPABILITY_MUTATING = "capability_mutating"
    MUTATION_REQUESTED = "mutation_requested"
    BUDGET_EXHAUSTED = "budget_exhausted"
    VALIDATED = "validated"


@dataclass(frozen=True, slots=True)
class AgentActionToolBudget:
    """Immutable, deterministic authorization budget for one controller run."""

    max_actions: int = 6
    actions_used: int = 0
    max_tools: int = 6
    tools_used: int = 0
    soft_search_queries: int = 3
    max_search_queries: int = 6
    search_queries_used: int = 0
    max_fetches: int = 6
    fetches_used: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("max_actions", self.max_actions),
            ("actions_used", self.actions_used),
            ("max_tools", self.max_tools),
            ("tools_used", self.tools_used),
            ("soft_search_queries", self.soft_search_queries),
            ("max_search_queries", self.max_search_queries),
            ("search_queries_used", self.search_queries_used),
            ("max_fetches", self.max_fetches),
            ("fetches_used", self.fetches_used),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")

    def permits_one_execution(self) -> bool:
        return (
            self.actions_used + 1 <= self.max_actions
            and self.tools_used + 1 <= self.max_tools
        )

    def after_execution(self) -> AgentActionToolBudget:
        """Return the next state; callers must only use it after execution."""
        if not self.permits_one_execution():
            raise ValueError("Cannot consume an exhausted action/tool budget.")
        return AgentActionToolBudget(
            max_actions=self.max_actions,
            actions_used=self.actions_used + 1,
            max_tools=self.max_tools,
            tools_used=self.tools_used + 1,
            soft_search_queries=self.soft_search_queries,
            max_search_queries=self.max_search_queries,
            search_queries_used=self.search_queries_used,
            max_fetches=self.max_fetches,
            fetches_used=self.fetches_used,
        )

    def permits_search_queries(self, count: int) -> bool:
        return (
            type(count) is int
            and count > 0
            and (self.search_queries_used + count <= self.max_search_queries)
        )

    def permits_fetch(self) -> bool:
        return self.fetches_used < self.max_fetches

    def after_search_execution(self, count: int) -> AgentActionToolBudget:
        if not self.permits_one_execution() or not self.permits_search_queries(count):
            raise ValueError("Cannot consume an exhausted Internet search budget.")
        return AgentActionToolBudget(
            max_actions=self.max_actions,
            actions_used=self.actions_used + 1,
            max_tools=self.max_tools,
            tools_used=self.tools_used + 1,
            soft_search_queries=self.soft_search_queries,
            max_search_queries=self.max_search_queries,
            search_queries_used=self.search_queries_used + count,
            max_fetches=self.max_fetches,
            fetches_used=self.fetches_used,
        )

    def after_fetch_execution(self) -> AgentActionToolBudget:
        if not self.permits_one_execution() or not self.permits_fetch():
            raise ValueError("Cannot consume an exhausted Internet fetch budget.")
        return AgentActionToolBudget(
            max_actions=self.max_actions,
            actions_used=self.actions_used + 1,
            max_tools=self.max_tools,
            tools_used=self.tools_used + 1,
            soft_search_queries=self.soft_search_queries,
            max_search_queries=self.max_search_queries,
            search_queries_used=self.search_queries_used,
            max_fetches=self.max_fetches,
            fetches_used=self.fetches_used + 1,
        )


@dataclass(frozen=True, slots=True)
class AgentActionValidationResult:
    """Safe normalized authorization output for one proposed action."""

    status: AgentActionValidationStatus
    reason: AgentActionValidationReason
    capability_id: str
    target_id: str | None = None
    source_family: str | None = None
    normalized_arguments: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )
    source_id: str | None = None
    calculator_request: CalculatorRequest | None = None
    internet_request: InternetActionRequest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, AgentActionValidationStatus):
            raise TypeError("status must be AgentActionValidationStatus.")
        if not isinstance(self.reason, AgentActionValidationReason):
            raise TypeError("reason must be AgentActionValidationReason.")
        if not isinstance(self.capability_id, str) or not self.capability_id:
            raise ValueError("capability_id must be non-empty text.")
        if self.target_id is not None and (
            not isinstance(self.target_id, str) or not self.target_id
        ):
            raise ValueError("target_id must be non-empty text or None.")
        if self.source_family is not None and (
            not isinstance(self.source_family, str) or not self.source_family
        ):
            raise ValueError("source_family must be non-empty text or None.")
        if self.source_id is not None and (
            not isinstance(self.source_id, str) or not self.source_id
        ):
            raise ValueError("source_id must be non-empty text or None.")
        if not isinstance(self.normalized_arguments, Mapping):
            raise TypeError("normalized_arguments must be a mapping.")
        if self.calculator_request is not None and not isinstance(
            self.calculator_request, CalculatorRequest
        ):
            raise TypeError("calculator_request must be a CalculatorRequest or None.")
        if self.internet_request is not None and not isinstance(
            self.internet_request, InternetActionRequest
        ):
            raise TypeError(
                "internet_request must be an InternetActionRequest or None."
            )
        object.__setattr__(
            self,
            "normalized_arguments",
            MappingProxyType(dict(self.normalized_arguments)),
        )

    @property
    def valid(self) -> bool:
        return self.status is AgentActionValidationStatus.VALID

    def to_trace_dict(self) -> dict[str, str | None]:
        """Return only identifiers/statuses, never parameter values."""
        return {
            "status": self.status.value,
            "reason": self.reason.value,
            "capability_id": self.capability_id,
            "target_id": self.target_id,
            "source_family": self.source_family,
            "source_id": self.source_id,
        }


class AgentActionValidator:
    """Validate exactly one v2 action in the required fail-closed order."""

    def __init__(
        self,
        discovery: ControllerCapabilityDiscovery,
        target_resolver: TargetResolver,
    ) -> None:
        if not isinstance(discovery, ControllerCapabilityDiscovery):
            raise TypeError("discovery must be ControllerCapabilityDiscovery.")
        if not isinstance(target_resolver, TargetResolver):
            raise TypeError("target_resolver must be TargetResolver.")
        self._discovery = discovery
        self._target_resolver = target_resolver
        self._read_only = ReadOnlyInspector()
        self._parameter_safety = ParameterSafetyInspector()

    @property
    def target_resolver(self) -> TargetResolver:
        """Expose exact-target authority to the narrow session-context adapter."""

        return self._target_resolver

    def validate(
        self,
        action: AgentAction,
        hard_constraints: HardRequestConstraints,
        budget: AgentActionToolBudget,
    ) -> AgentActionValidationResult:
        if not isinstance(action, AgentAction):
            raise TypeError("action must be AgentAction.")
        if not isinstance(hard_constraints, HardRequestConstraints):
            raise TypeError("hard_constraints must be HardRequestConstraints.")
        if not isinstance(budget, AgentActionToolBudget):
            raise TypeError("budget must be AgentActionToolBudget.")

        # 1. Exact capability ID exists and is available.  Empty constraints
        # intentionally defer source policy to the next required step.
        detail_result = self._discovery.selected_detail(
            action.capability_id, HardRequestConstraints()
        )
        if detail_result.status is CapabilityDetailStatus.UNKNOWN_CAPABILITY:
            return _result(
                AgentActionValidationStatus.REJECT,
                AgentActionValidationReason.CAPABILITY_UNKNOWN,
                action,
            )
        if detail_result.status is not CapabilityDetailStatus.DISCLOSED:
            return _result(
                AgentActionValidationStatus.UNAVAILABLE,
                AgentActionValidationReason.CAPABILITY_UNAVAILABLE,
                action,
            )
        schema = detail_result.selected_capability_schema
        if not isinstance(schema, Mapping):
            return _result(
                AgentActionValidationStatus.UNAVAILABLE,
                AgentActionValidationReason.CAPABILITY_UNAVAILABLE,
                action,
            )
        source_family = _schema_text(schema, "source_requirements", "family")
        target_kind = _schema_text(schema, "target_requirements", "kind")

        # 2. Hard source constraints and exclusions.
        if not _source_allowed(action, source_family, hard_constraints):
            return _result(
                AgentActionValidationStatus.REJECT,
                AgentActionValidationReason.SOURCE_FORBIDDEN,
                action,
                source_family=source_family,
            )

        source_id = _authorized_source_id(detail_result, source_family)
        if source_family in {"grafana", "zabbix", "internet"} and source_id is None:
            return _result(
                AgentActionValidationStatus.UNAVAILABLE,
                AgentActionValidationReason.CAPABILITY_UNAVAILABLE,
                action,
                source_family=source_family,
            )

        # 3-4. Capability target requirement, then exact registry/alias
        # resolution.  Neither branch parses prose or creates localhost.
        target_result = self._validate_target(
            action, hard_constraints.explicit_target, target_kind, source_family
        )
        if target_result is not None:
            return target_result
        target_id = _resolved_target(
            hard_constraints.explicit_target, self._target_resolver
        )

        # 5. Closed schema validation before any safety inspection.
        action_arguments: Mapping[str, object] = action.arguments
        if (
            action.capability_id == INTERNET_CURRENT_CAPABILITY_ID
            and set(action.arguments) == {"query"}
            and isinstance(action.arguments.get("query"), str)
        ):
            # Preserve the public single-query form without maintaining a
            # second execution path or weakening the disclosed batch schema.
            action_arguments = {"queries": [action.arguments["query"]]}
        normalized, failure = _validate_arguments(
            action_arguments, schema.get("arguments_schema")
        )
        if failure is not None:
            status, reason = failure
            return _result(status, reason, action, target_id, source_family)

        calculator_request: CalculatorRequest | None = None
        internet_request: InternetActionRequest | None = None
        if action.capability_id == CALCULATOR_CAPABILITY_ID:
            try:
                calculator_request = bind_calculator_action(normalized)
            except CalculatorActionBindingError as exc:
                return _result(
                    (
                        AgentActionValidationStatus.CLARIFY
                        if str(exc) == "missing_transport_fields"
                        else AgentActionValidationStatus.REJECT
                    ),
                    (
                        AgentActionValidationReason.ARGUMENT_REQUIRED
                        if str(exc) == "missing_transport_fields"
                        else AgentActionValidationReason.ARGUMENT_INVALID
                    ),
                    action,
                    target_id,
                    source_family,
                )

        # 6. Reuse the existing typed read-only and parameter safety guards.
        read_only = schema.get("read_only") is True
        resource = action.capability_id.rpartition(".")[2]
        inspection = self._read_only.inspect(
            InspectionContext(
                capability_name=resource,
                resource=resource,
                mutation_risk="none" if read_only else "high",
            )
        )
        if not inspection.allowed:
            return _result(
                AgentActionValidationStatus.REJECT,
                AgentActionValidationReason.CAPABILITY_MUTATING,
                action,
                target_id,
                source_family,
            )
        if hard_constraints.mutation_requested:
            return _result(
                AgentActionValidationStatus.REJECT,
                AgentActionValidationReason.MUTATION_REQUESTED,
                action,
                target_id,
                source_family,
            )
        safety = self._parameter_safety.inspect(
            InspectionContext(
                capability_name=resource,
                resource=resource,
                arguments=dict(normalized),
                mutation_risk="none",
            )
        )
        if not safety.allowed:
            return _result(
                AgentActionValidationStatus.REJECT,
                AgentActionValidationReason.ARGUMENT_UNSAFE,
                action,
                target_id,
                source_family,
            )

        # 7. Internet action semantics are closed and typed.  DNS, redirects,
        # and public-address checks deliberately remain in InternetTool.
        if action.capability_id in {
            INTERNET_CURRENT_CAPABILITY_ID,
            INTERNET_FETCH_URL_CAPABILITY_ID,
        }:
            try:
                internet_request = bind_internet_action(
                    action.capability_id, dict(normalized)
                )
            except InternetActionBindingError:
                return _result(
                    AgentActionValidationStatus.REJECT,
                    AgentActionValidationReason.URL_INVALID,
                    action,
                    target_id,
                    source_family,
                )
        if not _internet_action_allowed(
            action.capability_id, internet_request, hard_constraints
        ):
            return _result(
                AgentActionValidationStatus.REJECT,
                AgentActionValidationReason.URL_INVALID,
                action,
                target_id,
                source_family,
            )

        if internet_request is not None:
            allowed = (
                budget.permits_search_queries(len(internet_request.queries))
                if internet_request.kind.value == "current"
                else budget.permits_fetch()
            )
            if not allowed:
                return _result(
                    AgentActionValidationStatus.UNAVAILABLE,
                    AgentActionValidationReason.BUDGET_EXHAUSTED,
                    action,
                    target_id,
                    source_family,
                )

        # 8. This is a non-consuming authorization check.
        if not budget.permits_one_execution():
            return _result(
                AgentActionValidationStatus.UNAVAILABLE,
                AgentActionValidationReason.BUDGET_EXHAUSTED,
                action,
                target_id,
                source_family,
            )
        return AgentActionValidationResult(
            AgentActionValidationStatus.VALID,
            AgentActionValidationReason.VALIDATED,
            action.capability_id,
            target_id=target_id,
            source_family=source_family,
            normalized_arguments=normalized,
            source_id=source_id,
            calculator_request=calculator_request,
            internet_request=internet_request,
        )

    def _validate_target(
        self,
        action: AgentAction,
        reference: HardTargetReference | None,
        target_kind: str | None,
        source_family: str | None,
    ) -> AgentActionValidationResult | None:
        if target_kind == "machine" and reference is None:
            return _result(
                AgentActionValidationStatus.CLARIFY,
                AgentActionValidationReason.TARGET_REQUIRED,
                action,
                source_family=source_family,
            )
        if target_kind != "machine" and reference is not None:
            return _result(
                AgentActionValidationStatus.REJECT,
                AgentActionValidationReason.TARGET_MISMATCH,
                action,
                source_family=source_family,
            )
        if reference is None:
            return None
        resolved = _resolved_target(reference, self._target_resolver)
        if resolved is None:
            return _result(
                AgentActionValidationStatus.CLARIFY,
                AgentActionValidationReason.TARGET_UNKNOWN,
                action,
                source_family=source_family,
            )
        return None


def _result(
    status: AgentActionValidationStatus,
    reason: AgentActionValidationReason,
    action: AgentAction,
    target_id: str | None = None,
    source_family: str | None = None,
) -> AgentActionValidationResult:
    return AgentActionValidationResult(
        status, reason, action.capability_id, target_id, source_family
    )


def _resolved_target(
    reference: HardTargetReference | None,
    target_resolver: TargetResolver,
) -> str | None:
    if reference is None:
        return None
    resolved = target_resolver.resolve_exact_target_reference(reference.value)
    if resolved is None or reference.registered_target != resolved:
        return None
    return resolved


def _schema_text(schema: Mapping[str, object], key: str, nested_key: str) -> str | None:
    value = schema.get(key)
    if not isinstance(value, Mapping):
        return None
    nested = value.get(nested_key)
    return nested if isinstance(nested, str) else None


def _source_allowed(
    action: AgentAction,
    family: str | None,
    constraints: HardRequestConstraints,
) -> bool:
    if family in {None, "none", "compute"}:
        return True
    source_families = {
        value
        for constraint in constraints.source_constraints
        if (value := _source_family(constraint)) is not None
    }
    excluded = {
        value
        for constraint in constraints.excluded_sources
        if (value := _source_family(constraint)) is not None
    }
    if SourceConstraint.NO_INTERNET in constraints.source_constraints:
        excluded.add("internet")
    if family in excluded or (source_families and family not in source_families):
        return False
    if (
        family == "internet"
        and SourceConstraint.URL_ONLY in constraints.source_constraints
    ):
        return "url" in action.arguments
    return True


def _source_family(constraint: SourceConstraint) -> str | None:
    return {
        SourceConstraint.LINUX: "linux",
        SourceConstraint.SSH: "linux",
        SourceConstraint.GRAFANA: "grafana",
        SourceConstraint.ZABBIX: "zabbix",
        SourceConstraint.INTERNET: "internet",
        SourceConstraint.URL_ONLY: "internet",
    }.get(constraint)


def _authorized_source_id(
    detail_result: SelectedCapabilityDetailResult,
    source_family: str | None,
) -> str | None:
    """Return the single metadata-authorized source for source-backed actions."""

    if source_family not in {"grafana", "zabbix", "internet"}:
        return None
    source_ids = detail_result.source_ids
    return source_ids[0] if len(source_ids) == 1 else None


def _validate_arguments(
    arguments: Mapping[str, object], schema_value: object
) -> tuple[
    Mapping[str, object],
    tuple[AgentActionValidationStatus, AgentActionValidationReason] | None,
]:
    if not isinstance(schema_value, Mapping):
        return MappingProxyType({}), (
            AgentActionValidationStatus.REJECT,
            AgentActionValidationReason.ARGUMENT_INVALID,
        )
    properties = schema_value.get("properties")
    required = schema_value.get("required")
    if (
        not isinstance(properties, Mapping)
        or not isinstance(required, Sequence)
        or isinstance(required, (str, bytes))
    ):
        return MappingProxyType({}), (
            AgentActionValidationStatus.REJECT,
            AgentActionValidationReason.ARGUMENT_INVALID,
        )
    declared = set(properties)
    if any(not isinstance(name, str) for name in declared) or any(
        not isinstance(name, str) for name in required
    ):
        return MappingProxyType({}), (
            AgentActionValidationStatus.REJECT,
            AgentActionValidationReason.ARGUMENT_INVALID,
        )
    if set(arguments).difference(declared):
        return MappingProxyType({}), (
            AgentActionValidationStatus.REJECT,
            AgentActionValidationReason.ARGUMENT_UNDECLARED,
        )
    for name in required:
        property_schema = properties.get(name)
        if isinstance(property_schema, Mapping) and not _allows_null(property_schema):
            if name not in arguments or arguments[name] is None:
                return MappingProxyType({}), (
                    AgentActionValidationStatus.CLARIFY,
                    AgentActionValidationReason.ARGUMENT_REQUIRED,
                )
    normalized: dict[str, object] = {}
    for name, value in arguments.items():
        property_schema = properties.get(name)
        if not isinstance(property_schema, Mapping) or not _value_matches_schema(
            value, property_schema
        ):
            return MappingProxyType({}), (
                AgentActionValidationStatus.REJECT,
                AgentActionValidationReason.ARGUMENT_INVALID,
            )
        normalized[name] = value
    return MappingProxyType(normalized), None


def _allows_null(schema: Mapping[str, object]) -> bool:
    value_type = schema.get("type")
    return value_type == "null" or (
        isinstance(value_type, Sequence)
        and not isinstance(value_type, str)
        and "null" in value_type
    )


def _value_matches_schema(value: object, schema: Mapping[str, object]) -> bool:
    allowed_types = schema.get("type")
    types = (
        (allowed_types,)
        if isinstance(allowed_types, str)
        else tuple(allowed_types)
        if isinstance(allowed_types, Sequence)
        else ()
    )
    if not any(_matches_json_type(value, value_type) for value_type in types):
        return False
    enum = schema.get("enum")
    if (
        isinstance(enum, Sequence)
        and not isinstance(enum, (str, bytes))
        and value not in enum
    ):
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if (
            isinstance(minimum, (int, float))
            and not isinstance(minimum, bool)
            and value < minimum
        ):
            return False
        if (
            isinstance(maximum, (int, float))
            and not isinstance(maximum, bool)
            and value > maximum
        ):
            return False
    if _matches_json_type(value, "array"):
        minimum_items = schema.get("minItems")
        maximum_items = schema.get("maxItems")
        if isinstance(minimum_items, int) and len(value) < minimum_items:
            return False
        if isinstance(maximum_items, int) and len(value) > maximum_items:
            return False
        item_schema = schema.get("items")
        if item_schema is not None and (
            not isinstance(item_schema, Mapping)
            or not all(_value_matches_schema(item, item_schema) for item in value)
        ):
            return False
    pattern = schema.get("pattern")
    return not (
        isinstance(value, str)
        and isinstance(pattern, str)
        and re.fullmatch(pattern, value) is None
    )


def _matches_json_type(value: object, value_type: object) -> bool:
    return {
        "null": value is None,
        "string": isinstance(value, str),
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) in {int, float},
        "array": isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
    }.get(value_type, False)


def _internet_action_allowed(
    capability_id: str,
    request: InternetActionRequest | None,
    constraints: HardRequestConstraints,
) -> bool:
    """Enforce literal URL authority without reproducing SSRF policy."""

    if constraints.explicit_url is not None:
        return (
            capability_id == INTERNET_FETCH_URL_CAPABILITY_ID
            and request is not None
            and request.url == constraints.explicit_url
        )
    if capability_id in {
        INTERNET_CURRENT_CAPABILITY_ID,
        INTERNET_FETCH_URL_CAPABILITY_ID,
    }:
        return request is not None
    return True


__all__ = [
    "AgentActionToolBudget",
    "AgentActionValidationReason",
    "AgentActionValidationResult",
    "AgentActionValidationStatus",
    "AgentActionValidator",
]
