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


def test_disabled_sources_are_absent_and_fail_closed() -> None:
    registry = build_fake_registry(
        localhost=True
    )

    assert "zabbix" not in registry.target_names()

    with pytest.raises(KeyError):
        registry.get_tool("zabbix")


def test_environment_shares_registry_with_knowledge_tool() -> None:
    env = fake_environment(
        localhost=True,
        monitor=True,
        grafana=True,
    )

    assert env.knowledge_tool._registry is env.registry
    assert "monitor" in env.registry.target_names()


def test_fake_search_provider_queues_results_and_failures() -> None:
    provider = FakeSearchProvider(
        [
            search_response(
                "q1",
                "https://example.com/a",
            ),
            RuntimeError("provider down"),
        ]
    )

    first = provider.search("q1")

    assert first.status == "ok"
    assert first.results[0].url == (
        "https://example.com/a"
    )

    with pytest.raises(
        RuntimeError,
        match="provider down",
    ):
        provider.search("q2")
