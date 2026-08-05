from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def fact(
    metric: str,
    value: object,
    *,
    target: str = "server-1",
    subject: str = "system",
    validity: FactValidity = FactValidity.VALID,
    freshness: FactFreshness = FactFreshness.FRESH,
    unit: str = "percent",
) -> Fact:
    provenance = Provenance(
        source="test",
        capability=f"collect.{metric}",
        target=target,
        observed_at=NOW,
        command_ids=(f"cmd-{metric.replace('.', '-')}",),
    )
    return Fact(
        subject=subject,
        metric=metric,
        value=value,
        unit=unit,
        observed_at=NOW,
        collected_at=NOW,
        source="test",
        target=target,
        validity=validity,
        freshness=freshness,
        confidence=1.0,
        provenance=provenance,
    )
