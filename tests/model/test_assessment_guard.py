from __future__ import annotations

from datetime import datetime, timezone

from src.model.assessment_guard import apply_assessment_guards
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance


def _fact(metric: str, value: object, unit: str, target: str = "host1") -> Fact:
    now = datetime.now(timezone.utc)
    provenance = Provenance(
        id="prov:test", capability="cpu", source="linux", target=target, observed_at=now
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


def test_action_claim_short_circuits_everything() -> None:
    request = AssessmentRequest(raw_request="kiểm tra hệ thống")
    response = "Tôi đã xóa toàn bộ log cũ để giải phóng dung lượng."
    guarded = apply_assessment_guards(response, request)
    assert "chưa thực hiện" in guarded
    assert "xóa" not in guarded


def test_ungrounded_number_is_redacted() -> None:
    facts = (_fact("cpu.usage_percent", 42.5, "percent"),)
    request = AssessmentRequest(raw_request="kiểm tra CPU", facts=facts)
    response = "CPU hiện đang ở mức 99%."
    guarded = apply_assessment_guards(response, request)
    assert "99%" not in guarded


def test_grounded_response_passes_through_unchanged() -> None:
    facts = (_fact("cpu.usage_percent", 42.5, "percent"),)
    request = AssessmentRequest(raw_request="kiểm tra CPU", facts=facts)
    response = "CPU hiện đang ở mức 42.5%, không có gì bất thường."
    guarded = apply_assessment_guards(response, request)
    assert guarded == response


def test_claim_guard_rollback_keeps_action_safety_enabled() -> None:
    request = AssessmentRequest(raw_request="kiểm tra CPU")

    number_only = apply_assessment_guards(
        "CPU đang ở 99%.", request, enable_claim_guard=False
    )
    action_claim = apply_assessment_guards(
        "Tôi đã xóa toàn bộ log cũ.", request, enable_claim_guard=False
    )

    assert number_only == "CPU đang ở 99%."
    assert "chưa thực hiện" in action_claim
