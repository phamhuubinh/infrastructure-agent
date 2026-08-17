from __future__ import annotations

import pytest

from tests.fixtures.fake_environment import (
    FakeSearchProvider,
    build_fake_registry,
    fake_environment,
    search_response,
)


def test_registry_flags_produce_exact_availability_states() -> None:
    registry = build_fake_registry(
        localhost=True,
        monitor=True,
        ssh=True,
        grafana=True,
        zabbix=True,
        internet=True,
    )

    assert sorted(registry.target_names()) == [
        "grafana",
        "internet",
        "localhost",
        "monitor",
        "remote-1",
        "zabbix",
    ]
    assert registry.domain_tool_names() == ("grafana", "internet", "zabbix")
    assert registry.identity("monitor").backend_type == "local"
    assert registry.identity("remote-1").backend_type == "ssh"


def test_disabled_sources_are_absent_and_fail_closed() -> None:
    registry = build_fake_registry(localhost=True)

    assert "zabbix" not in registry.target_names()
    with pytest.raises(KeyError):
        registry.get_tool("zabbix")


def test_unknown_explicit_target_never_falls_back_to_localhost() -> None:
    from src.pipeline.semantic_plan_validation import SemanticPlanValidationStatus
    from tests.fixtures.fake_models import capability_plan

    env = fake_environment(localhost=True)

    result = env.target_resolver.validate_semantic_target(
        capability_plan(concept="cpu", target="ghost-host")
    )

    assert result.validation.status is SemanticPlanValidationStatus.CLARIFY
    assert result.resolved_target is None


def test_environment_builds_consistent_registry_resolver_and_tool() -> None:
    env = fake_environment(localhost=True, monitor=True, grafana=True)

    assert env.target_resolver._registry is env.registry
    assert env.knowledge_tool._registry is env.registry
    assert "monitor" in env.registry.target_names()


def test_domain_tools_carry_no_real_credentials() -> None:
    env = fake_environment(localhost=True, grafana=True, zabbix=True)

    grafana = env.registry.get_tool("grafana")
    zabbix = env.registry.get_tool("zabbix")
    assert ".invalid" in grafana._url
    assert ".invalid" in zabbix._url
    assert grafana._token == "fake-token"
    assert zabbix._token == "fake-token"


def test_fake_search_provider_queues_results_and_failures() -> None:
    provider = FakeSearchProvider(
        [
            search_response("q1", "https://example.com/a"),
            RuntimeError("provider down"),
        ]
    )

    first = provider.search("q1")

    assert first.status == "ok"
    assert first.results[0].url == "https://example.com/a"
    assert provider.queries == ["q1"]

    with pytest.raises(RuntimeError, match="provider down"):
        provider.search("q2")

    empty = provider.search("q3")
    assert empty.status == "empty"
    assert provider.queries == ["q1", "q2", "q3"]
