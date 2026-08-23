from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.evidence_package import (
    EvidencePackage,
)
from src.pipeline.fact import (
    Fact,
    FactFreshness,
    FactValidity,
)
from src.pipeline.provenance import Provenance


def test_package_serialization_excludes_raw_by_default() -> None:
    now = datetime.now(timezone.utc)
    provenance = Provenance(
        "linux",
        "get_cpu",
        "server-1",
        now,
    )

    fact = Fact(
        "system",
        "cpu.logical_cores",
        8,
        "count",
        now,
        now,
        "linux",
        "server-1",
        FactValidity.VALID,
        FactFreshness.FRESH,
        1.0,
        provenance,
    )

    package = EvidencePackage(
        "CPU Information",
        "CPU",
        raw_data={"large": "x" * 10_000},
        facts=(fact,),
    )

    default = package.to_dict()
    audited = package.to_dict(
        include_raw=True,
        raw_limit_bytes=100,
    )

    assert "raw_data" not in default
    assert (
        default["facts"][0]
        ["provenance"]["id"]
        == provenance.id
    )
    assert (
        audited["raw_data"]["truncated"]
        is True
    )


def test_small_raw_serialization_is_json_safe() -> None:
    package = EvidencePackage(
        "Clock",
        "Clock",
        raw_data={
            "at": datetime.now(
                timezone.utc
            )
        },
    )

    serialized = package.to_dict(
        include_raw=True
    )

    assert isinstance(
        serialized["raw_data"]["at"],
        str,
    )
