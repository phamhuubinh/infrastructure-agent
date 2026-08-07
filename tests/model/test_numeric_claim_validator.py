from __future__ import annotations

from datetime import datetime, timezone

from src.model.numeric_claim_validator import validate_numeric_consistency
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance


def _fact(metric: str, value: object, unit: str) -> Fact:
    now = datetime.now(timezone.utc)
    provenance = Provenance(
        id="prov:test", capability="disk", source="linux", target="host1", observed_at=now
    )
    return Fact(
        subject="host1",
        metric=metric,
        value=value,
        unit=unit,
        observed_at=now,
        collected_at=now,
        source="linux",
        target="host1",
        validity=FactValidity.VALID,
        freshness=FactFreshness.FRESH,
        confidence=1.0,
        provenance=provenance,
    )


def test_consistent_filesystem_facts_produce_no_issue() -> None:
    facts = (
        _fact("filesystem.size_bytes", 1000, "bytes"),
        _fact("filesystem.used_bytes", 600, "bytes"),
        _fact("filesystem.available_bytes", 400, "bytes"),
    )
    assert validate_numeric_consistency(facts) == ()


def test_inconsistent_filesystem_facts_flagged() -> None:
    facts = (
        _fact("filesystem.size_bytes", 1000, "bytes"),
        _fact("filesystem.used_bytes", 600, "bytes"),
        _fact("filesystem.available_bytes", 100, "bytes"),
    )
    issues = validate_numeric_consistency(facts)
    assert any(issue.kind == "arithmetic_mismatch" for issue in issues)
