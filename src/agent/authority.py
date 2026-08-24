"""Fail-closed authority boundary for canonical Orion Agent actions."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from src.agent.capabilities import (
    CapabilityDefinition,
    CapabilityRegistry,
)
from src.agent.contracts import AgentAction
from src.agent.permissions import EffectClass, PermissionMode


@dataclass(frozen=True, slots=True)
class ReferenceEntry:
    ref_id: str
    kind: str
    available: bool = True

    def __post_init__(self) -> None:
        for field_name in ("ref_id", "kind"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be non-empty text.")

        if type(self.available) is not bool:
            raise TypeError("available must be bool.")


class ExactReferenceRegistry:
    """Case-sensitive exact reference lookup with no aliases or defaults."""

    def __init__(
        self,
        entries: Sequence[ReferenceEntry],
    ) -> None:
        if any(not isinstance(item, ReferenceEntry) for item in entries):
            raise TypeError("entries must contain ReferenceEntry values.")

        ids = [item.ref_id for item in entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Reference IDs must be unique.")

        self._entries = tuple(entries)
        self._by_id = {item.ref_id: item for item in entries}

    @property
    def entries(self) -> tuple[ReferenceEntry, ...]:
        return self._entries

    def get(self, ref_id: str) -> ReferenceEntry | None:
        if not isinstance(ref_id, str):
            raise TypeError("ref_id must be a string.")
        return self._by_id.get(ref_id)


@dataclass(frozen=True, slots=True)
class ApprovalScope:
    """Structured approval. Goal text is audit/UI data, never parsed."""

    approval_id: str
    goal: str
    capability_ids: frozenset[str]
    target_refs: frozenset[str] = frozenset()
    source_refs: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.approval_id, str) or not self.approval_id:
            raise ValueError("approval_id must be non-empty text.")

        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("goal must be non-empty text.")

        for field_name in (
            "capability_ids",
            "target_refs",
            "source_refs",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, frozenset) or any(
                not isinstance(item, str) or not item for item in value
            ):
                raise TypeError(f"{field_name} must be frozenset[str].")

        if not self.capability_ids:
            raise ValueError("approval must contain at least one capability.")

    def covers(
        self,
        action: AgentAction,
    ) -> bool:
        if action.capability_id not in self.capability_ids:
            return False

        if self.target_refs and action.target_ref is None:
            return False

        if action.target_ref is not None and action.target_ref not in self.target_refs:
            return False

        if self.source_refs and action.source_ref is None:
            return False

        if action.source_ref is not None and action.source_ref not in self.source_refs:
            return False

        return True


@dataclass(frozen=True, slots=True)
class AuthorityBudget:
    max_actions: int = 6
    actions_used: int = 0
    max_cost: int = 12
    cost_used: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "max_actions",
            "actions_used",
            "max_cost",
            "cost_used",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")

        if self.actions_used > self.max_actions:
            raise ValueError("actions_used must not exceed max_actions.")

        if self.cost_used > self.max_cost:
            raise ValueError("cost_used must not exceed max_cost.")

    def permits(self, cost: int) -> bool:
        return (
            type(cost) is int
            and cost > 0
            and self.actions_used + 1 <= self.max_actions
            and self.cost_used + cost <= self.max_cost
        )

    def after_execution(
        self,
        cost: int,
    ) -> AuthorityBudget:
        if not self.permits(cost):
            raise ValueError("Cannot consume exhausted authority budget.")

        return AuthorityBudget(
            max_actions=self.max_actions,
            actions_used=self.actions_used + 1,
            max_cost=self.max_cost,
            cost_used=self.cost_used + cost,
        )


class AuthorizationStatus(str, Enum):
    VALID = "valid"
    APPROVAL_REQUIRED = "approval_required"
    REJECT = "reject"
    UNAVAILABLE = "unavailable"


class AuthorizationReason(str, Enum):
    VALIDATED = "validated"
    CAPABILITY_UNKNOWN = "capability_unknown"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    TARGET_REQUIRED = "target_required"
    TARGET_NOT_ALLOWED = "target_not_allowed"
    TARGET_UNKNOWN = "target_unknown"
    TARGET_UNAVAILABLE = "target_unavailable"
    TARGET_KIND_MISMATCH = "target_kind_mismatch"
    TARGET_NOT_SUPPORTED = "target_not_supported"
    SOURCE_REQUIRED = "source_required"
    SOURCE_NOT_ALLOWED = "source_not_allowed"
    SOURCE_UNKNOWN = "source_unknown"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_KIND_MISMATCH = "source_kind_mismatch"
    SOURCE_NOT_SUPPORTED = "source_not_supported"
    ARGUMENT_REQUIRED = "argument_required"
    ARGUMENT_UNDECLARED = "argument_undeclared"
    ARGUMENT_INVALID = "argument_invalid"
    EFFECT_BLOCKED = "effect_blocked"
    APPROVAL_MISSING = "approval_missing"
    SAFETY_NOT_REVIEWED = "safety_not_reviewed"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    status: AuthorizationStatus
    reason: AuthorizationReason
    capability_id: str
    effect: EffectClass | None = None
    target_ref: str | None = None
    source_ref: str | None = None
    normalized_arguments: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )
    budget_cost: int = 0
    approval_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "normalized_arguments",
            MappingProxyType(dict(self.normalized_arguments)),
        )

    @property
    def valid(self) -> bool:
        return self.status is AuthorizationStatus.VALID


class ActionAuthorizer:
    """Authorize one structured proposal in deterministic documented order."""

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        targets: ExactReferenceRegistry,
        sources: ExactReferenceRegistry,
    ) -> None:
        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError("capabilities must be CapabilityRegistry.")
        if not isinstance(targets, ExactReferenceRegistry):
            raise TypeError("targets must be ExactReferenceRegistry.")
        if not isinstance(sources, ExactReferenceRegistry):
            raise TypeError("sources must be ExactReferenceRegistry.")

        self._capabilities = capabilities
        self._targets = targets
        self._sources = sources

    @property
    def capabilities(self) -> CapabilityRegistry:
        return self._capabilities

    @property
    def targets(self) -> ExactReferenceRegistry:
        return self._targets

    @property
    def sources(self) -> ExactReferenceRegistry:
        return self._sources

    def authorize(
        self,
        action: AgentAction,
        *,
        permission_mode: PermissionMode,
        budget: AuthorityBudget,
        approval: ApprovalScope | None = None,
    ) -> AuthorizationResult:
        if not isinstance(action, AgentAction):
            raise TypeError("action must be AgentAction.")
        if not isinstance(permission_mode, PermissionMode):
            raise TypeError("permission_mode must be PermissionMode.")
        if not isinstance(budget, AuthorityBudget):
            raise TypeError("budget must be AuthorityBudget.")
        if approval is not None and not isinstance(
            approval,
            ApprovalScope,
        ):
            raise TypeError("approval must be ApprovalScope or None.")

        # 1. Exact capability lookup.
        capability = self._capabilities.get(action.capability_id)
        if capability is None:
            return _result(
                AuthorizationStatus.REJECT,
                AuthorizationReason.CAPABILITY_UNKNOWN,
                action,
            )

        # 2. Capability availability.
        if not capability.available:
            return _result(
                AuthorizationStatus.UNAVAILABLE,
                AuthorizationReason.CAPABILITY_UNAVAILABLE,
                action,
                capability,
            )

        # 3. Exact target/source lookup when required.
        reference_failure = self._validate_references(
            action,
            capability,
        )
        if reference_failure is not None:
            return reference_failure

        # 4. Closed schema validation.
        schema_reason = _validate_arguments(
            action.arguments,
            capability.arguments_schema,
        )
        if schema_reason is not None:
            return _result(
                AuthorizationStatus.REJECT,
                schema_reason,
                action,
                capability,
            )

        # 5. Effect permission.
        if not permission_mode.allows(capability.effect):
            return _result(
                AuthorizationStatus.REJECT,
                AuthorizationReason.EFFECT_BLOCKED,
                action,
                capability,
            )

        # 6. ASK approval scope.
        approval_id: str | None = None
        if permission_mode.requires_approval(capability.effect):
            if approval is None or not approval.covers(action):
                return _result(
                    AuthorizationStatus.APPROVAL_REQUIRED,
                    AuthorizationReason.APPROVAL_MISSING,
                    action,
                    capability,
                )
            approval_id = approval.approval_id

        # 7. Reviewed safety boundary.
        if not capability.safety_reviewed:
            return _result(
                AuthorizationStatus.UNAVAILABLE,
                AuthorizationReason.SAFETY_NOT_REVIEWED,
                action,
                capability,
                approval_id=approval_id,
            )

        # 8. Non-consuming resource-budget check.
        if not budget.permits(capability.budget_cost):
            return _result(
                AuthorizationStatus.UNAVAILABLE,
                AuthorizationReason.BUDGET_EXHAUSTED,
                action,
                capability,
                approval_id=approval_id,
            )

        return AuthorizationResult(
            status=AuthorizationStatus.VALID,
            reason=AuthorizationReason.VALIDATED,
            capability_id=action.capability_id,
            effect=capability.effect,
            target_ref=action.target_ref,
            source_ref=action.source_ref,
            normalized_arguments=dict(action.arguments),
            budget_cost=capability.budget_cost,
            approval_id=approval_id,
        )

    def _validate_references(
        self,
        action: AgentAction,
        capability: CapabilityDefinition,
    ) -> AuthorizationResult | None:
        target_reason = _reference_reason(
            action.target_ref,
            required_kind=capability.target_kind,
            registry=self._targets,
            required_reason=AuthorizationReason.TARGET_REQUIRED,
            not_allowed_reason=AuthorizationReason.TARGET_NOT_ALLOWED,
            unknown_reason=AuthorizationReason.TARGET_UNKNOWN,
            unavailable_reason=AuthorizationReason.TARGET_UNAVAILABLE,
            kind_mismatch_reason=(AuthorizationReason.TARGET_KIND_MISMATCH),
        )
        if target_reason is not None:
            return _result(
                _reference_status(target_reason),
                target_reason,
                action,
                capability,
            )

        if (
            action.target_ref is not None
            and capability.allowed_target_refs is not None
            and action.target_ref not in capability.allowed_target_refs
        ):
            return _result(
                AuthorizationStatus.REJECT,
                AuthorizationReason.TARGET_NOT_SUPPORTED,
                action,
                capability,
            )

        source_reason = _reference_reason(
            action.source_ref,
            required_kind=capability.source_kind,
            registry=self._sources,
            required_reason=AuthorizationReason.SOURCE_REQUIRED,
            not_allowed_reason=AuthorizationReason.SOURCE_NOT_ALLOWED,
            unknown_reason=AuthorizationReason.SOURCE_UNKNOWN,
            unavailable_reason=AuthorizationReason.SOURCE_UNAVAILABLE,
            kind_mismatch_reason=(AuthorizationReason.SOURCE_KIND_MISMATCH),
        )
        if source_reason is not None:
            return _result(
                _reference_status(source_reason),
                source_reason,
                action,
                capability,
            )

        if (
            action.source_ref is not None
            and capability.allowed_source_refs is not None
            and action.source_ref not in capability.allowed_source_refs
        ):
            return _result(
                AuthorizationStatus.REJECT,
                AuthorizationReason.SOURCE_NOT_SUPPORTED,
                action,
                capability,
            )

        return None


def _reference_reason(
    ref_id: str | None,
    *,
    required_kind: str | None,
    registry: ExactReferenceRegistry,
    required_reason: AuthorizationReason,
    not_allowed_reason: AuthorizationReason,
    unknown_reason: AuthorizationReason,
    unavailable_reason: AuthorizationReason,
    kind_mismatch_reason: AuthorizationReason,
) -> AuthorizationReason | None:
    if required_kind is None:
        return not_allowed_reason if ref_id is not None else None

    if ref_id is None:
        return required_reason

    entry = registry.get(ref_id)
    if entry is None:
        return unknown_reason

    if not entry.available:
        return unavailable_reason

    if entry.kind != required_kind:
        return kind_mismatch_reason

    return None


def _reference_status(
    reason: AuthorizationReason,
) -> AuthorizationStatus:
    if reason in {
        AuthorizationReason.TARGET_UNAVAILABLE,
        AuthorizationReason.SOURCE_UNAVAILABLE,
    }:
        return AuthorizationStatus.UNAVAILABLE
    return AuthorizationStatus.REJECT


def _result(
    status: AuthorizationStatus,
    reason: AuthorizationReason,
    action: AgentAction,
    capability: CapabilityDefinition | None = None,
    *,
    approval_id: str | None = None,
) -> AuthorizationResult:
    return AuthorizationResult(
        status=status,
        reason=reason,
        capability_id=action.capability_id,
        effect=(capability.effect if capability is not None else None),
        target_ref=action.target_ref,
        source_ref=action.source_ref,
        budget_cost=(capability.budget_cost if capability is not None else 0),
        approval_id=approval_id,
    )


def _validate_arguments(
    arguments: Mapping[str, object],
    schema: Mapping[str, object],
) -> AuthorizationReason | None:
    one_of = schema.get("oneOf")
    if isinstance(one_of, Sequence) and not isinstance(one_of, (str, bytes)):
        matches = [
            branch
            for branch in one_of
            if isinstance(branch, Mapping)
            and _validate_arguments(arguments, branch) is None
        ]
        if len(matches) == 1:
            return None
        return (
            AuthorizationReason.ARGUMENT_REQUIRED
            if any(
                isinstance(branch, Mapping)
                and _validate_arguments(arguments, branch)
                is AuthorizationReason.ARGUMENT_REQUIRED
                for branch in one_of
            )
            else AuthorizationReason.ARGUMENT_INVALID
        )

    properties = schema.get("properties")
    required = schema.get("required", [])

    if not isinstance(properties, Mapping):
        return AuthorizationReason.ARGUMENT_INVALID

    if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
        return AuthorizationReason.ARGUMENT_INVALID

    declared = set(properties)

    if set(arguments) - declared:
        return AuthorizationReason.ARGUMENT_UNDECLARED

    if any(name not in arguments for name in required):
        return AuthorizationReason.ARGUMENT_REQUIRED

    for name, value in arguments.items():
        child = properties.get(name)
        if not isinstance(child, Mapping) or not _value_matches_schema(value, child):
            return AuthorizationReason.ARGUMENT_INVALID

    return None


def _value_matches_schema(
    value: object,
    schema: Mapping[str, object],
) -> bool:
    raw_types = schema.get("type")
    if isinstance(raw_types, str):
        allowed_types = (raw_types,)
    elif isinstance(raw_types, Sequence) and not isinstance(raw_types, (str, bytes)):
        allowed_types = tuple(raw_types)
    else:
        return False

    if not any(_matches_json_type(value, value_type) for value_type in allowed_types):
        return False

    enum = schema.get("enum")
    if (
        isinstance(enum, Sequence)
        and not isinstance(enum, (str, bytes))
        and not any(
            type(value) is type(candidate) and value == candidate for candidate in enum
        )
    ):
        return False

    if isinstance(value, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        pattern = schema.get("pattern")

        if isinstance(minimum, int) and len(value) < minimum:
            return False
        if isinstance(maximum, int) and len(value) > maximum:
            return False
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
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

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        items = schema.get("items")

        if isinstance(minimum, int) and len(value) < minimum:
            return False
        if isinstance(maximum, int) and len(value) > maximum:
            return False
        if items is not None and (
            not isinstance(items, Mapping)
            or not all(_value_matches_schema(item, items) for item in value)
        ):
            return False

    if isinstance(value, Mapping):
        return (
            _validate_arguments(
                value,
                schema,
            )
            is None
        )

    return True


def _matches_json_type(
    value: object,
    value_type: object,
) -> bool:
    if not isinstance(value_type, str):
        return False

    return {
        "null": value is None,
        "string": isinstance(value, str),
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) in {int, float},
        "array": (isinstance(value, Sequence) and not isinstance(value, (str, bytes))),
        "object": isinstance(value, Mapping),
    }.get(value_type, False)
