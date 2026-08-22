from __future__ import annotations

import inspect

import pytest

from src.agent.controller_contracts import AgentAction
from src.pipeline.agent_action_validator import (
    AgentActionToolBudget,
    AgentActionValidationReason,
    AgentActionValidationStatus,
    AgentActionValidator,
)
from src.pipeline.controller_capability_discovery import ControllerCapabilityDiscovery
from src.pipeline.hard_request_constraints import (
    HardRequestConstraints,
    HardTargetReference,
)
from src.pipeline.request_semantics import SourceConstraint
from tests.fixtures.fake_environment import fake_environment


def _validator(**flags: object) -> AgentActionValidator:
    environment = fake_environment(**flags)
    return AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(environment.knowledge_tool),
        environment.target_resolver,
    )


def _host_constraints(target: str = "localhost") -> HardRequestConstraints:
    return HardRequestConstraints(
        explicit_target=HardTargetReference(target, registered_target=target)
    )


def _validate(
    action: AgentAction,
    constraints: HardRequestConstraints | None = None,
    **flags: object,
):
    return _validator(**flags).validate(
        action, constraints or _host_constraints(), AgentActionToolBudget()
    )


def test_valid_host_action_is_authorized_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = fake_environment()
    discovery = ControllerCapabilityDiscovery.from_knowledge_tool(
        environment.knowledge_tool
    )
    validator = AgentActionValidator(discovery, environment.target_resolver)
    execution_calls = 0

    def execute(_arguments: dict[str, object]) -> None:
        nonlocal execution_calls
        execution_calls += 1

    monkeypatch.setattr(environment.knowledge_tool, "execute", execute)

    result = validator.validate(
        AgentAction("host.get_listening_ports", {"port": 443}),
        _host_constraints(),
        AgentActionToolBudget(),
    )
    invalid_result = validator.validate(
        AgentAction("host.does_not_exist"),
        _host_constraints(),
        AgentActionToolBudget(),
    )

    assert execution_calls == 0
    assert result.status is AgentActionValidationStatus.VALID
    assert result.reason is AgentActionValidationReason.VALIDATED
    assert result.target_id == "localhost"
    assert result.normalized_arguments == {"port": 443}
    assert "port" not in result.to_trace_dict()
    assert invalid_result.reason is AgentActionValidationReason.CAPABILITY_UNKNOWN


@pytest.mark.parametrize(
    ("action", "expected_status", "expected_reason"),
    (
        (
            AgentAction("host.does_not_exist"),
            AgentActionValidationStatus.REJECT,
            AgentActionValidationReason.CAPABILITY_UNKNOWN,
        ),
        (
            AgentAction("grafana.metrics"),
            AgentActionValidationStatus.UNAVAILABLE,
            AgentActionValidationReason.CAPABILITY_UNAVAILABLE,
        ),
    ),
)
def test_unknown_and_unavailable_capabilities_fail_closed(
    action: AgentAction,
    expected_status: AgentActionValidationStatus,
    expected_reason: AgentActionValidationReason,
) -> None:
    result = _validate(action)

    assert result.status is expected_status
    assert result.reason is expected_reason


def test_explicit_unknown_target_never_defaults_to_localhost() -> None:
    result = _validate(
        AgentAction("host.get_listening_ports", {"port": 443}),
        HardRequestConstraints(
            explicit_target=HardTargetReference("ghost-host", registered_target=None)
        ),
    )

    assert result.status is AgentActionValidationStatus.CLARIFY
    assert result.reason is AgentActionValidationReason.TARGET_UNKNOWN
    assert result.target_id is None


def test_target_mismatch_is_not_silently_corrected() -> None:
    result = _validate(
        AgentAction("internet.current", {"query": "Orion"}),
        HardRequestConstraints(
            explicit_target=HardTargetReference(
                "localhost", registered_target="localhost"
            )
        ),
        internet=True,
    )

    assert result.status is AgentActionValidationStatus.REJECT
    assert result.reason is AgentActionValidationReason.TARGET_MISMATCH
    assert result.capability_id == "internet.current"


@pytest.mark.parametrize("source", ("grafana", "zabbix"))
def test_source_backed_monitoring_capability_rejects_linux_machine_target(
    source: str,
) -> None:
    action = AgentAction(
        f"{source}.dashboards" if source == "grafana" else "zabbix.get_hosts"
    )
    result = _validate(action, _host_constraints(), **{source: True})

    assert result.status is AgentActionValidationStatus.REJECT
    assert result.reason is AgentActionValidationReason.TARGET_MISMATCH
    assert result.target_id is None


def test_source_backed_grafana_capability_uses_source_authority_not_machine_target() -> (
    None
):
    result = _validate(
        AgentAction("grafana.dashboards"),
        HardRequestConstraints(source_constraints=(SourceConstraint.GRAFANA,)),
        grafana=True,
    )

    assert result.status is AgentActionValidationStatus.VALID
    assert result.target_id is None
    assert result.source_family == "grafana"


def test_grafana_only_and_source_exclusions_reject_host_capability() -> None:
    action = AgentAction("host.get_listening_ports", {"port": 443})

    grafana_only = _validate(
        action,
        HardRequestConstraints(
            explicit_target=HardTargetReference(
                "localhost", registered_target="localhost"
            ),
            source_constraints=(SourceConstraint.GRAFANA,),
        ),
        grafana=True,
    )
    excluded = _validate(
        action,
        HardRequestConstraints(
            explicit_target=HardTargetReference(
                "localhost", registered_target="localhost"
            ),
            excluded_sources=(SourceConstraint.LINUX,),
        ),
    )

    assert grafana_only.reason is AgentActionValidationReason.SOURCE_FORBIDDEN
    assert excluded.reason is AgentActionValidationReason.SOURCE_FORBIDDEN


def test_url_only_and_literal_url_authority_are_enforced() -> None:
    literal_url = "https://example.com/release"
    url_only = HardRequestConstraints(
        explicit_url=literal_url,
        source_constraints=(SourceConstraint.URL_ONLY,),
    )

    search = _validate(
        AgentAction("internet.current", {"query": "Orion release"}),
        url_only,
        internet=True,
    )
    matching_fetch = _validate(
        AgentAction("internet.fetch_url", {"url": literal_url}),
        url_only,
        internet=True,
    )
    different_fetch = _validate(
        AgentAction("internet.fetch_url", {"url": "https://example.com/other"}),
        url_only,
        internet=True,
    )
    ordinary_search = _validate(
        AgentAction("internet.current", {"query": "Orion release"}),
        HardRequestConstraints(),
        internet=True,
    )

    assert search.reason is AgentActionValidationReason.SOURCE_FORBIDDEN
    assert matching_fetch.status is AgentActionValidationStatus.VALID
    assert different_fetch.status is AgentActionValidationStatus.REJECT
    assert different_fetch.reason is AgentActionValidationReason.URL_INVALID
    assert ordinary_search.status is AgentActionValidationStatus.VALID


def test_explicit_url_requires_exact_fetch_url_action() -> None:
    url = "https://example.com/release"
    constraints = HardRequestConstraints(explicit_url=url)

    current = _validate(
        AgentAction("internet.current", {"query": "release"}),
        constraints,
        internet=True,
    )
    wrong = _validate(
        AgentAction("internet.fetch_url", {"url": "https://example.com/other"}),
        constraints,
        internet=True,
    )
    exact = _validate(
        AgentAction("internet.fetch_url", {"url": url}), constraints, internet=True
    )

    assert current.reason is AgentActionValidationReason.URL_INVALID
    assert wrong.reason is AgentActionValidationReason.URL_INVALID
    assert exact.status is AgentActionValidationStatus.VALID


def test_argument_schema_enforces_required_type_enum_bounds_and_declared_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = fake_environment()
    tool = environment.knowledge_tool
    monkeypatch.setattr(
        tool,
        "get_capability_metadata",
        lambda: {
            "localhost": [
                {
                    "name": "strict_parameters",
                    "description": "Read strict fixture data",
                    "parameters": ["source", "resource", "count", "mode", "name"],
                    "parameter_specs": [
                        {
                            "name": "count",
                            "required": True,
                            "value_type": "int",
                            "enum": [],
                            "minimum": 1,
                            "maximum": 3,
                        },
                        {
                            "name": "mode",
                            "required": True,
                            "value_type": "str",
                            "enum": ["safe", "fast"],
                            "minimum": None,
                            "maximum": None,
                        },
                        {
                            "name": "name",
                            "required": False,
                            "value_type": "str",
                            "enum": [],
                            "minimum": None,
                            "maximum": None,
                        },
                    ],
                    "mutation_risk": "none",
                }
            ]
        },
    )
    monkeypatch.setattr(tool, "source_kind", lambda _source: "linux")
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(tool),
        environment.target_resolver,
    )

    def validate(arguments: dict[str, object]):
        return validator.validate(
            AgentAction("host.strict_parameters", arguments),
            _host_constraints(),
            AgentActionToolBudget(),
        )

    assert (
        validate({"mode": "safe"}).reason
        is AgentActionValidationReason.ARGUMENT_REQUIRED
    )
    assert (
        validate({"count": "1", "mode": "safe"}).reason
        is AgentActionValidationReason.ARGUMENT_INVALID
    )
    assert (
        validate({"count": 4, "mode": "safe"}).reason
        is AgentActionValidationReason.ARGUMENT_INVALID
    )
    assert (
        validate({"count": 1, "mode": "unsafe"}).reason
        is AgentActionValidationReason.ARGUMENT_INVALID
    )
    assert (
        validate({"count": 1, "mode": "safe", "extra": 1}).reason
        is AgentActionValidationReason.ARGUMENT_UNDECLARED
    )
    assert (
        validate({"count": 1, "mode": "safe"}).status
        is AgentActionValidationStatus.VALID
    )


def test_mutating_capability_and_mutating_argument_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = fake_environment()
    tool = environment.knowledge_tool
    monkeypatch.setattr(
        tool,
        "get_capability_metadata",
        lambda: {
            "localhost": [
                {
                    "name": "mutating_fixture",
                    "description": "Mutating fixture",
                    "parameters": [],
                    "parameter_specs": [],
                    "mutation_risk": "high",
                },
                {
                    "name": "read_name",
                    "description": "Read fixture name",
                    "parameters": ["source", "resource", "name"],
                    "parameter_specs": [
                        {
                            "name": "name",
                            "required": True,
                            "value_type": "str",
                            "enum": [],
                            "minimum": None,
                            "maximum": None,
                        }
                    ],
                    "mutation_risk": "none",
                },
            ]
        },
    )
    monkeypatch.setattr(tool, "source_kind", lambda _source: "linux")
    validator = AgentActionValidator(
        ControllerCapabilityDiscovery.from_knowledge_tool(tool),
        environment.target_resolver,
    )

    def validate(action: AgentAction):
        return validator.validate(action, _host_constraints(), AgentActionToolBudget())

    assert (
        validate(AgentAction("host.mutating_fixture")).reason
        is AgentActionValidationReason.CAPABILITY_MUTATING
    )
    assert (
        validate(AgentAction("host.read_name", {"name": "rm -rf /tmp/x"})).reason
        is AgentActionValidationReason.ARGUMENT_UNSAFE
    )


def test_budget_exhaustion_and_validator_dependency_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.pipeline.normalizer as normalizer
    import src.pipeline.request_semantics as request_semantics

    monkeypatch.setattr(
        normalizer, "Normalizer", lambda: (_ for _ in ()).throw(AssertionError)
    )
    monkeypatch.setattr(
        request_semantics,
        "RequestSemanticsClassifier",
        lambda: (_ for _ in ()).throw(AssertionError),
    )
    validator = _validator()
    action = AgentAction("host.get_listening_ports", {"port": 443})

    budget_result = validator.validate(
        action,
        _host_constraints(),
        AgentActionToolBudget(max_actions=1, actions_used=1),
    )
    valid_result = validator.validate(
        action, _host_constraints(), AgentActionToolBudget()
    )

    assert budget_result.status is AgentActionValidationStatus.UNAVAILABLE
    assert budget_result.reason is AgentActionValidationReason.BUDGET_EXHAUSTED
    assert valid_result.status is AgentActionValidationStatus.VALID
    assert "Normalizer" not in inspect.getsource(AgentActionValidator)
    assert "RequestSemanticsClassifier" not in inspect.getsource(AgentActionValidator)
