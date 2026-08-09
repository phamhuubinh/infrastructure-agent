from __future__ import annotations

from datetime import datetime, timezone

from src.model.claim_validator import (
    ClaimValidator,
    redact_ungrounded_claims,
    redact_ungrounded_external_claims,
)
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance


def _fact(metric: str, value: object, unit: str, target: str = "host1") -> Fact:
    now = datetime.now(timezone.utc)
    provenance = Provenance(
        id="prov:test",
        capability="cpu",
        source="linux",
        target=target,
        observed_at=now,
    )
    return Fact(
        subject=target,
        metric=metric,
        value=value,
        unit=unit,
        observed_at=now,
        collected_at=now,
        source="linux",
        target=target,
        validity=FactValidity.VALID,
        freshness=FactFreshness.FRESH,
        confidence=1.0,
        provenance=provenance,
    )


def _request(facts: tuple[Fact, ...]) -> AssessmentRequest:
    return AssessmentRequest(raw_request="kiểm tra CPU host1", facts=facts)


def test_grounded_number_passes() -> None:
    facts = (_fact("cpu.usage_percent", 42.5, "percent"),)
    result = ClaimValidator().validate("CPU đang ở mức 42.5%.", _request(facts))
    assert result.grounded


def test_ungrounded_number_flagged() -> None:
    facts = (_fact("cpu.usage_percent", 42.5, "percent"),)
    result = ClaimValidator().validate("CPU đang ở mức 99%.", _request(facts))
    assert not result.grounded
    assert result.ungrounded_numbers


def test_no_evidence_means_nothing_to_ground() -> None:
    result = ClaimValidator().validate(
        "CPU đang ở mức 99%.", AssessmentRequest(raw_request="x")
    )
    assert result.grounded


def test_redact_ungrounded_claims_replaces_invented_number() -> None:
    facts = (_fact("cpu.usage_percent", 42.5, "percent"),)
    request = _request(facts)
    redacted = redact_ungrounded_claims("CPU đang ở mức 99%.", request)
    assert "99%" not in redacted
    assert "chưa xác nhận" in redacted


def test_redact_keeps_grounded_number() -> None:
    facts = (_fact("cpu.usage_percent", 42.5, "percent"),)
    request = _request(facts)
    redacted = redact_ungrounded_claims("CPU đang ở mức 42.5%.", request)
    assert "42.5%" in redacted


def test_external_current_claim_requires_extracted_page_content() -> None:
    request = AssessmentRequest(
        raw_request="Phiên bản Python mới nhất là gì?",
        intent="EXTERNAL_VERIFICATION",
        evidence=(
            EvidencePackage(
                capability_name="external_verification",
                evidence_name="external_current",
                data={
                    "documents": [
                        {
                            "content": "The supported release is Python 3.14.1.",
                            "relevance": "sufficient",
                        }
                    ]
                },
                source="internet",
            ),
        ),
    )

    guarded = redact_ungrounded_external_claims(
        "Phiên bản mới nhất là 3.99.0.", request
    )

    assert "3.99.0" not in guarded
    assert "chưa xác nhận" in guarded


def test_external_current_claim_keeps_value_present_in_extracted_content() -> None:
    request = AssessmentRequest(
        raw_request="Phiên bản Python mới nhất là gì?",
        intent="EXTERNAL_VERIFICATION",
        evidence=(
            EvidencePackage(
                capability_name="external_verification",
                evidence_name="external_current",
                data={
                    "documents": [
                        {
                            "content": "Python 3.14.1 is available.",
                            "relevance": "sufficient",
                        }
                    ]
                },
                source="internet",
            ),
        ),
    )

    assert "3.14.1" in redact_ungrounded_external_claims(
        "Phiên bản là 3.14.1.", request
    )
