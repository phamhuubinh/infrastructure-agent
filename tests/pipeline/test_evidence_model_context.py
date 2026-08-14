from __future__ import annotations

import json
from datetime import datetime, timezone

from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_model_context import (
    EvidenceModelContextBudget,
    EvidenceModelContextSerializer,
)
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance


def _fact(
    fact_id: str,
    value: int,
    *,
    source: str = "linux",
    target: str = "monitor",
    validity: FactValidity = FactValidity.VALID,
) -> Fact:
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    return Fact(
        subject="system",
        metric="cpu.usage_percent",
        value=value if validity is FactValidity.VALID else None,
        unit="percent",
        observed_at=now,
        collected_at=now,
        source=source,
        target=target,
        validity=validity,
        freshness=FactFreshness.FRESH,
        confidence=1.0,
        provenance=Provenance(
            source=source,
            capability="get_cpu",
            target=target,
            observed_at=now,
            source_reference="https://example.com/cpu?token=secret",
        ),
        id=fact_id,
    )


def test_compaction_prefers_facts_and_preserves_identity_and_contradictions() -> None:
    valid = _fact("fact:valid", 20)
    contradictory = _fact(
        "fact:contradictory",
        30,
        source="grafana",
        validity=FactValidity.CONTRADICTORY,
    )
    package = EvidencePackage(
        "CPU",
        "CPU Usage",
        data={"huge": "x" * 50_000},
        facts=(valid, contradictory),
        source="linux",
    )
    request = AssessmentRequest(
        raw_request="check cpu on monitor",
        evidence=(package,),
        facts=(valid, contradictory),
        evidence_status="CONTRADICTORY",
    )

    context = EvidenceModelContextSerializer().serialize(request)

    facts = context["facts"]
    assert facts[0]["validity"] == "contradictory"
    assert {item["target"] for item in facts} == {"monitor"}
    assert {item["source"] for item in facts} == {"linux", "grafana"}
    assert all("provenance" in item for item in facts)
    assert "raw" not in context["packages"][0]


def test_compaction_is_stable_bounded_and_redacts_raw_secrets() -> None:
    package = EvidencePackage(
        "Internet",
        "Current Information",
        data={
            "authorization": "Bearer top-secret",
            "content": "api_key=supersecret " + "x" * 5_000,
            "items": list(range(50)),
            "unrelated": {f"key-{index}": index for index in range(50)},
        },
    )
    request = AssessmentRequest(
        raw_request="latest version",
        evidence=(package,),
        raw_evidence_required=True,
    )
    budget = EvidenceModelContextBudget(
        max_bytes=1_500,
        max_raw_items=3,
        max_text_chars=80,
    )
    serializer = EvidenceModelContextSerializer(budget)

    first = serializer.to_json(request)
    second = serializer.to_json(request)

    assert first == second
    assert len(first.encode("utf-8")) <= budget.max_bytes
    assert "top-secret" not in first
    assert "supersecret" not in first
    assert "<redacted>" in first
    decoded = json.loads(first)
    assert decoded["packages"][0]["raw"]["authorization"] == "<redacted>"
    assert decoded["packages"][0]["raw"]["items"][-1]["_omitted_items"] == 47


def test_item_budget_reports_deterministic_omissions() -> None:
    facts = tuple(_fact(f"fact:{index}", index + 1) for index in range(5))
    request = AssessmentRequest(raw_request="cpu", facts=facts)
    context = EvidenceModelContextSerializer(
        EvidenceModelContextBudget(max_facts=2)
    ).serialize(request)

    assert [item["id"] for item in context["facts"]] == ["fact:0", "fact:1"]
    assert context["omitted"]["facts"] == 3


def test_raw_payload_requires_explicit_assessment_permission() -> None:
    package = EvidencePackage("Provider", "Factless", data={"value": 1})

    context = EvidenceModelContextSerializer().serialize(
        AssessmentRequest(raw_request="inspect", evidence=(package,))
    )

    assert "raw" not in context["packages"][0]
    assert context["omitted"]["raw_packages"] == 1
