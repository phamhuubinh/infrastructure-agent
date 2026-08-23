from __future__ import annotations

import inspect

import pytest

from src.agent.authority import (
    ActionAuthorizer,
    ApprovalScope,
    AuthorizationReason,
    AuthorizationStatus,
    AuthorityBudget,
    ExactReferenceRegistry,
    ReferenceEntry,
)
from src.agent.capabilities import (
    CapabilityDefinition,
    CapabilityRegistry,
)
from src.agent.contracts import AgentAction
from src.agent.permissions import EffectClass, PermissionMode


def _schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "window": {
                "type": "integer",
                "minimum": 1,
                "maximum": 300,
            },
        },
        "required": ["window"],
    }


def _capability(
    *,
    capability_id: str = "host.cpu",
    effect: EffectClass = EffectClass.READ,
    target_kind: str | None = "machine",
    source_kind: str | None = None,
    available: bool = True,
    safety_reviewed: bool = True,
    budget_cost: int = 1,
    allowed_target_refs: frozenset[str] | None = None,
    allowed_source_refs: frozenset[str] | None = None,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        purpose="Inspect host CPU",
        tool_id="linux",
        effect=effect,
        arguments_schema=_schema(),
        runtime_binding="linux.cpu",
        target_kind=target_kind,
        source_kind=source_kind,
        allowed_target_refs=allowed_target_refs,
        allowed_source_refs=allowed_source_refs,
        available=available,
        safety_reviewed=safety_reviewed,
        budget_cost=budget_cost,
        result_kind="host_state",
        activity_label="Checking CPU",
    )


def _authorizer(
    *capabilities: CapabilityDefinition,
) -> ActionAuthorizer:
    return ActionAuthorizer(
        CapabilityRegistry(capabilities),
        ExactReferenceRegistry(
            (
                ReferenceEntry("monitor", "machine"),
                ReferenceEntry("server01", "machine"),
                ReferenceEntry(
                    "offline-host",
                    "machine",
                    available=False,
                ),
            )
        ),
        ExactReferenceRegistry(
            (
                ReferenceEntry("grafana-prod", "grafana"),
                ReferenceEntry("zabbix-main", "zabbix"),
            )
        ),
    )


def _action(
    *,
    capability_id: str = "host.cpu",
    target_ref: str | None = "monitor",
    source_ref: str | None = None,
    window: object = 60,
) -> AgentAction:
    return AgentAction(
        capability_id=capability_id,
        target_ref=target_ref,
        source_ref=source_ref,
        arguments={"window": window},
    )


def test_capability_lookup_is_exact_and_case_sensitive() -> None:
    result = _authorizer(_capability()).authorize(
        _action(capability_id="Host.cpu"),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert result.status is AuthorizationStatus.REJECT
    assert (
        result.reason
        is AuthorizationReason.CAPABILITY_UNKNOWN
    )


def test_target_is_required_without_default_localhost() -> None:
    result = _authorizer(_capability()).authorize(
        _action(target_ref=None),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert result.reason is AuthorizationReason.TARGET_REQUIRED


def test_target_lookup_is_exact_without_fuzzy_alias() -> None:
    result = _authorizer(_capability()).authorize(
        _action(target_ref="Monitor"),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert result.reason is AuthorizationReason.TARGET_UNKNOWN


def test_unavailable_target_fails_closed() -> None:
    result = _authorizer(_capability()).authorize(
        _action(target_ref="offline-host"),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert result.status is AuthorizationStatus.UNAVAILABLE
    assert (
        result.reason
        is AuthorizationReason.TARGET_UNAVAILABLE
    )


def test_source_lookup_is_exact_and_kind_checked() -> None:
    capability = _capability(
        capability_id="grafana.metrics",
        target_kind=None,
        source_kind="grafana",
    )
    authorizer = _authorizer(capability)

    missing = authorizer.authorize(
        _action(
            capability_id="grafana.metrics",
            target_ref=None,
            source_ref=None,
        ),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )
    assert missing.reason is AuthorizationReason.SOURCE_REQUIRED

    wrong_kind = authorizer.authorize(
        _action(
            capability_id="grafana.metrics",
            target_ref=None,
            source_ref="zabbix-main",
        ),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )
    assert (
        wrong_kind.reason
        is AuthorizationReason.SOURCE_KIND_MISMATCH
    )


def test_reference_is_rejected_when_capability_does_not_use_it() -> None:
    capability = _capability(target_kind=None)

    result = _authorizer(capability).authorize(
        _action(target_ref="monitor"),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert (
        result.reason
        is AuthorizationReason.TARGET_NOT_ALLOWED
    )


@pytest.mark.parametrize(
    ("arguments", "reason"),
    (
        ({}, AuthorizationReason.ARGUMENT_REQUIRED),
        (
            {"window": 60, "extra": True},
            AuthorizationReason.ARGUMENT_UNDECLARED,
        ),
        (
            {"window": 0},
            AuthorizationReason.ARGUMENT_INVALID,
        ),
        (
            {"window": "60"},
            AuthorizationReason.ARGUMENT_INVALID,
        ),
    ),
)
def test_closed_schema_is_authority(
    arguments: dict[str, object],
    reason: AuthorizationReason,
) -> None:
    action = AgentAction(
        capability_id="host.cpu",
        target_ref="monitor",
        arguments=arguments,
    )

    result = _authorizer(_capability()).authorize(
        action,
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert result.reason is reason


def test_read_mode_allows_read_and_blocks_write() -> None:
    read = _authorizer(_capability()).authorize(
        _action(),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )
    assert read.valid

    write_capability = _capability(
        capability_id="host.restart",
        effect=EffectClass.WRITE,
    )
    write = _authorizer(write_capability).authorize(
        _action(capability_id="host.restart"),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert write.status is AuthorizationStatus.REJECT
    assert write.reason is AuthorizationReason.EFFECT_BLOCKED


def test_rw_ask_requires_exact_scoped_approval() -> None:
    capability = _capability(
        capability_id="host.restart",
        effect=EffectClass.WRITE,
    )
    authorizer = _authorizer(capability)
    action = _action(capability_id="host.restart")

    missing = authorizer.authorize(
        action,
        permission_mode=PermissionMode.RW_ASK,
        budget=AuthorityBudget(),
    )
    assert (
        missing.status
        is AuthorizationStatus.APPROVAL_REQUIRED
    )

    wrong_target = ApprovalScope(
        approval_id="approval-1",
        goal="Restart the declared host.",
        capability_ids=frozenset({"host.restart"}),
        target_refs=frozenset({"server01"}),
    )
    still_missing = authorizer.authorize(
        action,
        permission_mode=PermissionMode.RW_ASK,
        budget=AuthorityBudget(),
        approval=wrong_target,
    )
    assert (
        still_missing.status
        is AuthorizationStatus.APPROVAL_REQUIRED
    )

    exact = ApprovalScope(
        approval_id="approval-2",
        goal="Restart the declared host.",
        capability_ids=frozenset({"host.restart"}),
        target_refs=frozenset({"monitor"}),
    )
    allowed = authorizer.authorize(
        action,
        permission_mode=PermissionMode.RW_ASK,
        budget=AuthorityBudget(),
        approval=exact,
    )

    assert allowed.valid
    assert allowed.approval_id == "approval-2"


def test_rw_full_allows_valid_reviewed_write_without_approval() -> None:
    capability = _capability(
        capability_id="host.restart",
        effect=EffectClass.WRITE,
    )

    result = _authorizer(capability).authorize(
        _action(capability_id="host.restart"),
        permission_mode=PermissionMode.RW_FULL,
        budget=AuthorityBudget(),
    )

    assert result.valid
    assert result.effect is EffectClass.WRITE


def test_unreviewed_capability_cannot_execute() -> None:
    result = _authorizer(
        _capability(safety_reviewed=False)
    ).authorize(
        _action(),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert result.status is AuthorizationStatus.UNAVAILABLE
    assert (
        result.reason
        is AuthorizationReason.SAFETY_NOT_REVIEWED
    )


def test_budget_is_checked_without_being_consumed() -> None:
    capability = _capability(budget_cost=3)
    authorizer = _authorizer(capability)

    exhausted = authorizer.authorize(
        _action(),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(
            max_actions=2,
            actions_used=1,
            max_cost=3,
            cost_used=1,
        ),
    )
    assert (
        exhausted.reason
        is AuthorizationReason.BUDGET_EXHAUSTED
    )

    budget = AuthorityBudget(max_actions=2, max_cost=5)
    valid = authorizer.authorize(
        _action(),
        permission_mode=PermissionMode.READ,
        budget=budget,
    )

    assert valid.valid
    assert budget.actions_used == 0
    assert budget.cost_used == 0

    consumed = budget.after_execution(
        valid.budget_cost
    )
    assert consumed.actions_used == 1
    assert consumed.cost_used == 3


def test_capability_schema_itself_must_be_closed() -> None:
    with pytest.raises(
        ValueError,
        match="additionalProperties=false",
    ):
        CapabilityDefinition(
            capability_id="host.cpu",
            purpose="Inspect host CPU",
            tool_id="linux",
            effect=EffectClass.READ,
            arguments_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
            runtime_binding="linux.cpu",
        )


def test_unsupported_schema_keywords_fail_closed() -> None:
    with pytest.raises(
        ValueError,
        match="unsupported keywords",
    ):
        CapabilityDefinition(
            capability_id="host.cpu",
            purpose="Inspect host CPU",
            tool_id="linux",
            effect=EffectClass.READ,
            arguments_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {},
                "required": [],
                "unevaluatedProperties": False,
            },
            runtime_binding="linux.cpu",
        )


def test_duplicate_registries_fail_closed() -> None:
    capability = _capability()

    with pytest.raises(ValueError, match="unique"):
        CapabilityRegistry((capability, capability))

    with pytest.raises(ValueError, match="unique"):
        ExactReferenceRegistry(
            (
                ReferenceEntry("monitor", "machine"),
                ReferenceEntry("monitor", "machine"),
            )
        )


def test_authorizer_has_no_natural_language_constraint_input() -> None:
    parameters = inspect.signature(
        ActionAuthorizer.authorize
    ).parameters

    assert "hard_constraints" not in parameters
    assert "raw_request" not in parameters
    assert "semantic_plan" not in parameters



def test_exact_registered_ref_must_be_supported_by_capability() -> None:
    target_scoped = _capability(
        allowed_target_refs=frozenset({"monitor"}),
    )

    wrong_target = _authorizer(target_scoped).authorize(
        _action(target_ref="server01"),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    assert (
        wrong_target.reason
        is AuthorizationReason.TARGET_NOT_SUPPORTED
    )

    source_scoped = _capability(
        capability_id="grafana.metrics",
        target_kind=None,
        source_kind="grafana",
        allowed_source_refs=frozenset({"grafana-prod"}),
    )

    wrong_source = _authorizer(source_scoped).authorize(
        _action(
            capability_id="grafana.metrics",
            target_ref=None,
            source_ref="zabbix-main",
        ),
        permission_mode=PermissionMode.READ,
        budget=AuthorityBudget(),
    )

    # Kind mismatch fails before capability scope.
    assert (
        wrong_source.reason
        is AuthorizationReason.SOURCE_KIND_MISMATCH
    )



def test_approval_scope_does_not_cover_missing_scoped_reference() -> None:
    capability = _capability(
        capability_id="system.write",
        effect=EffectClass.WRITE,
        target_kind=None,
    )
    authorizer = _authorizer(capability)

    approval = ApprovalScope(
        approval_id="approval-scoped",
        goal="Write only on monitor.",
        capability_ids=frozenset({"system.write"}),
        target_refs=frozenset({"monitor"}),
    )

    result = authorizer.authorize(
        _action(
            capability_id="system.write",
            target_ref=None,
        ),
        permission_mode=PermissionMode.RW_ASK,
        budget=AuthorityBudget(),
        approval=approval,
    )

    assert (
        result.status
        is AuthorizationStatus.APPROVAL_REQUIRED
    )
    assert (
        result.reason
        is AuthorizationReason.APPROVAL_MISSING
    )


def test_capability_requires_closed_object_root_schema() -> None:
    with pytest.raises(
        ValueError,
        match="closed object schema",
    ):
        CapabilityDefinition(
            capability_id="host.invalid",
            purpose="Invalid schema",
            tool_id="linux",
            effect=EffectClass.READ,
            arguments_schema={
                "type": "string",
            },
            runtime_binding="linux.invalid",
        )
