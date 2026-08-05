from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _provenance() -> Provenance:
    return Provenance(
        source="linux",
        capability="get_cpu_usage",
        target="server-1",
        observed_at=NOW,
        command_ids=("command-1",),
    )


def test_fact_is_immutable_and_json_serializable() -> None:
    fact = Fact(
        subject="system",
        metric="cpu.usage",
        value={"percent": 42},
        unit="percent",
        observed_at=NOW,
        collected_at=NOW,
        source="linux",
        target="server-1",
        validity=FactValidity.VALID,
        freshness=FactFreshness.FRESH,
        confidence=1.0,
        provenance=_provenance(),
    )

    with pytest.raises(FrozenInstanceError):
        fact.metric = "memory.usage"  # type: ignore[misc]
    with pytest.raises(TypeError):
        fact.value["percent"] = 0  # type: ignore[index]
    assert json.loads(json.dumps(fact.to_dict()))["metric"] == "cpu.usage"


def test_valid_fact_requires_canonical_metric_and_explicit_unit() -> None:
    kwargs = {
        "subject": "system",
        "value": 1,
        "observed_at": NOW,
        "collected_at": NOW,
        "source": "linux",
        "target": "server-1",
        "validity": FactValidity.VALID,
        "freshness": FactFreshness.FRESH,
        "confidence": 1.0,
        "provenance": _provenance(),
    }
    with pytest.raises(ValueError):
        Fact(metric="CPU Usage", unit="percent", **kwargs)
    with pytest.raises(ValueError):
        Fact(metric="cpu.usage", unit="", **kwargs)


def test_zero_is_only_allowed_as_a_valid_observation() -> None:
    with pytest.raises(ValueError):
        Fact(
            subject="swap",
            metric="swap.total",
            value=0,
            unit="byte",
            observed_at=NOW,
            collected_at=NOW,
            source="linux",
            target="server-1",
            validity=FactValidity.COMMAND_FAILED,
            freshness=FactFreshness.FRESH,
            confidence=1.0,
            provenance=_provenance(),
        )
