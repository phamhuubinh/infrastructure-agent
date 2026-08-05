from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.fact_reconciler import FactReconciler, MetricTolerance
from src.pipeline.provenance import Provenance

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _fact(source: str, value: float) -> Fact:
    return Fact(
        "filesystem:/var",
        "filesystem.available",
        value,
        "byte",
        NOW,
        NOW,
        source,
        "server-1",
        FactValidity.VALID,
        FactFreshness.FRESH,
        1.0,
        Provenance(source, "capacity", "server-1", NOW),
    )


def test_conflicting_same_window_facts_are_retained_and_marked() -> None:
    result = FactReconciler(
        tolerances={"filesystem.available": MetricTolerance(relative=0.01)}
    ).reconcile((_fact("linux", 100), _fact("zabbix", 150)))

    assert result.contradictory is True
    assert len(result.fact_set.facts) == 2
    assert all(fact.validity is FactValidity.CONTRADICTORY for fact in result.fact_set)
    assert result.contradictions[0].sources == ("linux", "zabbix")


def test_values_within_tolerance_remain_valid() -> None:
    result = FactReconciler(
        tolerances={"filesystem.available": MetricTolerance(absolute=5)}
    ).reconcile((_fact("linux", 100), _fact("grafana", 103)))

    assert result.contradictions == ()
    assert all(fact.validity is FactValidity.VALID for fact in result.fact_set)
