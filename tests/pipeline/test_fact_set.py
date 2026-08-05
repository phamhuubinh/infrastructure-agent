from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.fact_set import FactSet, FactSetBuilder
from src.pipeline.provenance import Provenance

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _fact(metric: str, source: str, value: float) -> Fact:
    provenance = Provenance(source, "collector", "server-1", NOW)
    return Fact(
        "system",
        metric,
        value,
        "percent",
        NOW,
        NOW,
        source,
        "server-1",
        FactValidity.VALID,
        FactFreshness.FRESH,
        1.0,
        provenance,
    )


def test_parallel_merge_order_is_deterministic_and_indexed() -> None:
    cpu = _fact("cpu.usage", "linux", 20)
    memory = _fact("memory.usage", "linux", 30)

    left = FactSet.merge((cpu,), (memory,))
    right = FactSet.merge((memory,), (cpu,))

    assert left.facts == right.facts
    assert left.by_metric("cpu.usage") == (cpu,)
    assert left.by_target("server-1") == left.facts


def test_builder_is_append_only_and_builds_new_immutable_set() -> None:
    builder = FactSetBuilder().add(_fact("cpu.usage", "linux", 20))
    first = builder.build()
    builder.add(_fact("memory.usage", "linux", 30))

    assert len(first) == 1
    assert len(builder.build()) == 2
