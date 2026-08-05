from __future__ import annotations

from datetime import datetime, timezone

from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance


def test_package_serialization_is_auditable_and_excludes_raw_by_default() -> None:
    now = datetime.now(timezone.utc)
    provenance = Provenance("linux", "get_cpu", "server-1", now)
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
        collection_failures=("optional probe failed",),
        schema_version="linux.v1",
    )

    default = package.to_dict()
    audited = package.to_dict(include_raw=True, raw_limit_bytes=100)

    assert "raw_data" not in default
    assert default["facts"][0]["provenance"]["id"] == provenance.id
    assert default["collection_failures"] == ["optional probe failed"]
    assert audited["raw_data"]["truncated"] is True


def test_small_raw_serialization_is_json_safe() -> None:
    package = EvidencePackage(
        "Clock", "Clock", raw_data={"at": datetime.now(timezone.utc)}
    )

    serialized = package.to_dict(include_raw=True)

    assert isinstance(serialized["raw_data"]["at"], str)


def test_assessment_places_canonical_facts_before_legacy_raw() -> None:
    now = datetime.now(timezone.utc)
    provenance = Provenance("linux", "get_cpu", "server-1", now)
    fact = Fact(
        "system",
        "cpu.usage",
        20,
        "percent",
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
        "CPU",
        "CPU",
        raw_data={"legacy_raw_sentinel": 20},
        facts=(fact,),
    )
    prompt = build_assessment_prompt(
        AssessmentRequest(raw_request="cpu", evidence=(package,), facts=(fact,))
    )

    assert prompt.index("--- Canonical facts ---") < prompt.index("--- Evidence ---")
    assert "legacy_raw_sentinel" not in prompt
