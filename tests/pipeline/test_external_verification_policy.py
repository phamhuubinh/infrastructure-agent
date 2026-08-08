from src.pipeline.external_verification_policy import (
    ExternalVerificationDecision,
    ExternalVerificationPolicy,
)
from src.pipeline.normalizer import Normalizer


def test_stable_knowledge_needs_no_external_verification() -> None:
    result = ExternalVerificationPolicy().decide(
        Normalizer().normalize("TCP và UDP khác nhau thế nào?")
    )

    assert result.decision is ExternalVerificationDecision.NONE


def test_current_fact_requires_external_verification() -> None:
    result = ExternalVerificationPolicy().decide(
        Normalizer().normalize("CEO hiện tại của Microsoft là ai?")
    )

    assert result.decision is ExternalVerificationDecision.REQUIRED
    assert result.requires_verification


def test_explicit_online_request_is_distinct_from_currentness() -> None:
    result = ExternalVerificationPolicy().decide(
        Normalizer().normalize("Hãy kiểm tra trên Internet lịch phát hành Python.")
    )

    assert result.decision is ExternalVerificationDecision.EXPLICIT


def test_explicit_url_has_its_own_external_decision() -> None:
    result = ExternalVerificationPolicy().decide(
        Normalizer().normalize("Đọc https://example.com")
    )

    assert result.decision is ExternalVerificationDecision.URL


def test_no_internet_constraint_blocks_external_requirement() -> None:
    result = ExternalVerificationPolicy().decide(
        Normalizer().normalize("Giá Bitcoin hiện tại, không dùng Internet.")
    )

    assert result.decision is ExternalVerificationDecision.REQUIRED
    assert result.blocked_by_source_constraint
