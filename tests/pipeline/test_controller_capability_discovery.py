from __future__ import annotations

import json

from src.agent.controller_contracts import AgentAction, AgentRunState
from src.model.protocol.controller_prompt import (
    ControllerContinuationInput,
    build_controller_prompt,
)
from src.pipeline.controller_capability_discovery import (
    MAX_DISCOVERY_PAYLOAD_BYTES,
    MAX_DISCOVERY_SUMMARIES_PER_CATEGORY,
    MAX_SELECTED_CAPABILITY_DETAIL_BYTES,
    CapabilityDetailStatus,
    CapabilityDiscoveryStatus,
    ControllerCapabilityDiscovery,
)
from src.pipeline.hard_request_constraints import HardRequestConstraints
from src.pipeline.request_semantics import SourceConstraint
from src.tool.knowledge_tool import KnowledgeTool
from tests.fixtures.fake_environment import build_fake_registry


def _discovery(**flags: object) -> ControllerCapabilityDiscovery:
    return ControllerCapabilityDiscovery.from_knowledge_tool(
        KnowledgeTool(build_fake_registry(**flags))
    )


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value)) if value else set()
    return set()


def test_direct_first_turn_has_no_capability_disclosure_payload() -> None:
    prompt = build_controller_prompt(
        "Hello.", hard_constraints=HardRequestConstraints()
    )

    payload = json.loads(prompt.user_prompt)

    assert "capability_summaries" not in payload
    assert "selected_capability_schema" not in payload


def test_host_discovery_returns_only_bounded_host_summaries_in_order() -> None:
    result = _discovery(grafana=True, zabbix=True, internet=True).discover(
        "host", HardRequestConstraints()
    )

    assert result.status is CapabilityDiscoveryStatus.DISCOVERED
    assert result.category == "host"
    assert result.summaries
    assert len(result.summaries) == MAX_DISCOVERY_SUMMARIES_PER_CATEGORY
    assert [item["capability_id"] for item in result.summaries] == sorted(
        item["capability_id"] for item in result.summaries
    )
    assert all(item["source_family"] == "linux" for item in result.summaries)
    assert all(item["target_kind"] == "machine" for item in result.summaries)
    assert len(json.dumps(result.to_payload()).encode()) <= MAX_DISCOVERY_PAYLOAD_BYTES


def test_grafana_hard_constraint_excludes_host_alternatives() -> None:
    discovery = _discovery(grafana=True)
    constraints = HardRequestConstraints(source_constraints=(SourceConstraint.GRAFANA,))

    host = discovery.discover("host", constraints)
    grafana = discovery.discover("grafana", constraints)

    assert host.status is CapabilityDiscoveryStatus.UNAVAILABLE_CATEGORY
    assert grafana.status is CapabilityDiscoveryStatus.DISCOVERED
    assert all(item["source_family"] == "grafana" for item in grafana.summaries)


def test_selected_detail_exposes_one_closed_schema_compatible_with_controller_prompt() -> (
    None
):
    discovery = _discovery()

    result = discovery.selected_detail(
        "host.get_listening_ports", HardRequestConstraints()
    )

    assert result.status is CapabilityDetailStatus.DISCLOSED
    selected = result.selected_capability_schema
    assert selected is not None
    assert set(selected) == {
        "capability_id",
        "arguments_schema",
        "target_requirements",
        "source_requirements",
        "usage",
        "availability",
        "read_only",
    }
    arguments_schema = selected["arguments_schema"]
    assert arguments_schema == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "port": {
                "type": ["integer", "null"],
                "minimum": 1,
                "maximum": 65535,
            }
        },
        "required": ["port"],
    }
    assert len(json.dumps(selected).encode()) <= MAX_SELECTED_CAPABILITY_DETAIL_BYTES

    continuation = ControllerContinuationInput(
        run_state=AgentRunState(raw_request="List port 443."),
        selected_capability_schema=selected,
    )
    prompt = build_controller_prompt(
        "List port 443.",
        hard_constraints=HardRequestConstraints(),
        continuation=continuation,
    )
    assert json.loads(prompt.user_prompt)["selected_capability_schema"] == selected


def test_optional_metadata_arguments_are_nullable_in_the_strict_transport_schema(
    monkeypatch,
) -> None:
    tool = KnowledgeTool(build_fake_registry())
    monkeypatch.setattr(
        tool,
        "get_capability_metadata",
        lambda: {
            "fixture-host": [
                {
                    "name": "mixed_parameters",
                    "description": "Read fixture measurements",
                    "parameters": [
                        "source",
                        "resource",
                        "required_count",
                        "optional_limit",
                        "optional_mode",
                    ],
                    "parameter_specs": [
                        {
                            "name": "required_count",
                            "required": True,
                            "value_type": "int",
                            "default": None,
                            "has_default": False,
                            "enum": [],
                            "minimum": 1,
                            "maximum": 10,
                        },
                        {
                            "name": "optional_limit",
                            "required": False,
                            "value_type": "int",
                            "default": 5,
                            "has_default": True,
                            "enum": [],
                            "minimum": 1,
                            "maximum": 20,
                        },
                        {
                            "name": "optional_mode",
                            "required": False,
                            "value_type": "str",
                            "default": "safe",
                            "has_default": True,
                            "enum": ["fast", "safe"],
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
    discovery = ControllerCapabilityDiscovery.from_knowledge_tool(tool)

    result = discovery.selected_detail(
        "host.mixed_parameters", HardRequestConstraints()
    )

    assert result.status is CapabilityDetailStatus.DISCLOSED
    selected = result.selected_capability_schema
    assert selected is not None
    schema = selected["arguments_schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "optional_limit",
        "optional_mode",
        "required_count",
    ]
    assert schema["properties"] == {
        "optional_limit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 20,
        },
        "optional_mode": {
            "type": ["string", "null"],
            "enum": ["fast", "safe", None],
        },
        "required_count": {"type": "integer", "minimum": 1, "maximum": 10},
    }
    assert (
        AgentAction(
            "host.mixed_parameters",
            {"required_count": 3, "optional_limit": None, "optional_mode": None},
        ).arguments["optional_mode"]
        is None
    )
    assert AgentAction("host.mixed_parameters", {"required_count": 3}).arguments == {
        "required_count": 3
    }
    ControllerContinuationInput(
        run_state=AgentRunState(raw_request="Read fixture measurements."),
        selected_capability_schema=selected,
    )


def test_unknown_and_unavailable_results_are_stable_and_do_not_substitute() -> None:
    discovery = _discovery(grafana=True)

    assert discovery.discover("database", HardRequestConstraints()).to_payload() == {
        "status": "unknown_category"
    }
    assert discovery.selected_detail(
        "host.does_not_exist", HardRequestConstraints()
    ).to_payload() == {"status": "unknown_capability"}

    unavailable = discovery.selected_detail(
        "host.get_cpu",
        HardRequestConstraints(source_constraints=(SourceConstraint.GRAFANA,)),
    )
    assert unavailable.status is CapabilityDetailStatus.UNAVAILABLE_CAPABILITY
    assert unavailable.to_payload() == {
        "status": "unavailable_capability",
        "capability_id": "host.get_cpu",
    }

    missing_grafana = _discovery().selected_detail(
        "grafana.metrics", HardRequestConstraints()
    )
    assert missing_grafana.to_payload() == {
        "status": "unavailable_capability",
        "capability_id": "grafana.metrics",
    }


def test_calculator_discovery_exposes_the_canonical_deterministic_action() -> None:
    discovery = _discovery()

    result = discovery.discover("calculator", HardRequestConstraints())

    assert result.status is CapabilityDiscoveryStatus.DISCOVERED
    assert result.summaries == (
        {
            "capability_id": "compute.deterministic",
            "purpose": "Perform exact deterministic computation",
            "source_family": "compute",
            "availability": "available",
            "read_only": True,
            "typed_arguments_required": True,
        },
    )
    detail = discovery.selected_detail(
        "compute.deterministic", HardRequestConstraints()
    )
    assert detail.status is CapabilityDetailStatus.DISCLOSED
    assert detail.source_ids == ()
    assert detail.selected_capability_schema is not None
    assert detail.selected_capability_schema["target_requirements"] == {
        "kind": "none",
        "required": False,
    }
    assert detail.selected_capability_schema["source_requirements"] == {
        "family": "compute",
        "required": False,
    }
    constrained = discovery.discover(
        "calculator",
        HardRequestConstraints(source_constraints=(SourceConstraint.GRAFANA,)),
    )
    assert constrained.status is CapabilityDiscoveryStatus.DISCOVERED


def test_unrelated_capabilities_do_not_inflate_host_discovery() -> None:
    host_only = _discovery().discover("host", HardRequestConstraints()).to_payload()
    all_sources = (
        _discovery(grafana=True, zabbix=True, internet=True)
        .discover("host", HardRequestConstraints())
        .to_payload()
    )

    assert all_sources == host_only


def test_disclosure_payloads_expose_no_command_credential_or_endpoint_fields() -> None:
    discovery = _discovery(grafana=True, zabbix=True, internet=True)
    discovery_payload = discovery.discover(
        "internet", HardRequestConstraints()
    ).to_payload()
    detail = discovery.selected_detail(
        "internet.web_fetch", HardRequestConstraints()
    ).to_payload()

    forbidden = {"command", "commands", "credential", "credentials", "endpoint", "url"}
    assert not (_keys(discovery_payload) & forbidden)
    assert not (_keys(detail) & (forbidden - {"url"}))
    assert (
        "url" in detail["selected_capability_schema"]["arguments_schema"]["properties"]
    )
