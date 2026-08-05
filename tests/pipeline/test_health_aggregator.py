from __future__ import annotations

from src.pipeline.fact_set import FactSet
from src.pipeline.health_aggregator import HealthAggregator, HealthStatus
from tests.pipeline.reasoning_fact_factory import fact


def test_active_problem_overrides_enabled_host_and_healthy_metrics() -> None:
    facts = FactSet(
        (
            fact(
                "monitoring.problem_active",
                {"active": True, "name": "DHCP link down", "severity": "high"},
                unit="event",
            ),
            fact("monitoring.host_enabled", True, unit="boolean"),
            fact("cpu.usage", 10.0),
        )
    )

    summary = HealthAggregator().aggregate(facts)

    assert summary.status is HealthStatus.CRITICAL
    assert summary.healthy is False
    assert summary.targets[0].active_incident_fact_ids


def test_empty_fact_scope_is_unavailable_not_healthy() -> None:
    summary = HealthAggregator().aggregate(FactSet(), default_target="server-1")

    assert summary.status is HealthStatus.UNAVAILABLE
