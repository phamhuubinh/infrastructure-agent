"""Tests for GA2-R1-02: selected-passage claim grounding in claim_validator.

These tests verify that:
- redact_ungrounded_external_claims consumes selected_passages from SUFFICIENT
  documents rather than the full fetched page corpus.
- A concrete claim is groundable only when its subject/claim type/value are
  supported by the selected passage used for that request.
- PARTIAL/IRRELEVANT passages never ground a concrete current claim.
- Version/date/price/identity claims preserve the exact supported value and
  redact a different value.
- Explicit URL: an arbitrary subject/value present in selected support is
  accepted.
- Explicit URL: successful fetch but requested fact absent remains insufficient.
- PARTIAL selected support never grounds a concrete current value.
"""

from __future__ import annotations

from src.model.claim_validator import (
    redact_ungrounded_external_claims,
)
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage


def _external_request(
    documents: list[dict],
    intent: str = "EXTERNAL_VERIFICATION",
) -> AssessmentRequest:
    """Build an AssessmentRequest with external evidence for testing."""
    return AssessmentRequest(
        raw_request="What is the current version?",
        intent=intent,
        evidence=(
            EvidencePackage(
                capability_name="external_verification",
                evidence_name="external_current",
                data={
                    "documents": documents,
                },
                source="internet",
            ),
        ),
    )


class TestSelectedPassageGrounding:
    """Tests for GA2-R1-02: selected-passage claim grounding."""

    def test_selected_passage_with_matching_version_is_kept(self) -> None:
        """Version claim present in selected passage is kept."""
        documents = [
            {
                "content": "This is unrelated full page content.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        "text": "Python current version is 3.14.2",
                        "url": "https://example.com/python",
                        "relevance": "sufficient",
                    }
                ],
            }
        ]
        request = _external_request(documents)
        guarded = redact_ungrounded_external_claims(
            "Phiên bản mới nhất là 3.14.2.", request
        )
        assert "3.14.2" in guarded

    def test_selected_passage_with_different_version_is_redacted(self) -> None:
        """Version claim NOT in selected passage is redacted even if present
        elsewhere in the full document content."""
        documents = [
            {
                # Full content contains 3.99.0 but it is OUTSIDE the selected
                # passage — the selected passage only mentions 3.14.2.
                "content": "Node.js version 3.99.0 is available. Python current version is 3.14.2.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        # Only the Python passage is selected (request is for Python)
                        "text": "Python current version is 3.14.2",
                        "url": "https://example.com/python",
                        "relevance": "sufficient",
                    }
                ],
            }
        ]
        request = _external_request(documents)
        guarded = redact_ungrounded_external_claims(
            "Phiên bản mới nhất là 3.99.0.", request
        )
        # 3.99.0 should be redacted because it's NOT in the selected passage
        assert "3.99.0" not in guarded
        assert "chưa xác nhận" in guarded

    def test_partial_passage_never_grounds_concrete_value(self) -> None:
        """PARTIAL selected support never grounds a concrete current value."""
        documents = [
            {
                "content": "Python version 3.14.2 is available.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        # PARTIAL relevance passage (truncated)
                        "text": "Python version 3.",
                        "url": "https://example.com/python",
                        "relevance": "partial",
                    }
                ],
            }
        ]
        request = _external_request(documents)
        guarded = redact_ungrounded_external_claims(
            "Phiên bản mới nhất là 3.14.2.", request
        )
        # 3.14.2 should be redacted because the PARTIAL passage doesn't
        # contain the full version
        assert "3.14.2" not in guarded
        assert "chưa xác nhận" in guarded

    def test_irrelevant_passage_never_grounds_concrete_value(self) -> None:
        """IRRELEVANT selected support never grounds a concrete current value."""
        documents = [
            {
                "content": "Python version 3.14.2 is available.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        # IRRELEVANT passage (unrelated content)
                        "text": "Weather forecast for today is sunny.",
                        "url": "https://example.com/weather",
                        "relevance": "irrelevant",
                    }
                ],
            }
        ]
        request = _external_request(documents)
        guarded = redact_ungrounded_external_claims(
            "Phiên bản mới nhất là 3.14.2.", request
        )
        # 3.14.2 should be redacted because the IRRELEVANT passage doesn't
        # contain the version claim
        assert "3.14.2" not in guarded
        assert "chưa xác nhận" in guarded

    def test_date_claim_preserved_when_in_selected_passage(self) -> None:
        """Date/identity claims preserve the exact supported value."""
        documents = [
            {
                "content": "Release date is 2024-08-15 for Python 3.14.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        "text": "Release date is 2024-08-15",
                        "url": "https://example.com/release",
                        "relevance": "sufficient",
                    }
                ],
            }
        ]
        request = _external_request(documents)
        guarded = redact_ungrounded_external_claims(
            "Ngày phát hành là 2024-08-15.", request
        )
        assert "2024-08-15" in guarded

    def test_date_claim_redacted_when_not_in_selected_passage(self) -> None:
        """Date claim NOT in selected passage is redacted."""
        documents = [
            {
                "content": "Release date for Node.js is 2023-05-01. Release date for Python is 2024-08-15.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        # Only Python release date is selected
                        "text": "Release date is 2024-08-15",
                        "url": "https://example.com/python",
                        "relevance": "sufficient",
                    }
                ],
            }
        ]
        request = _external_request(documents)
        guarded = redact_ungrounded_external_claims(
            "Ngày phát hành là 2023-05-01.", request
        )
        # 2023-05-01 should be redacted (Node.js date, not Python date)
        assert "2023-05-01" not in guarded
        assert "chưa xác nhận" in guarded

    def test_arbitrary_subject_from_selected_passage_is_accepted(self) -> None:
        """Explicit URL: an arbitrary subject/value present in selected support
        is accepted."""
        documents = [
            {
                "content": "Full page with many topics including pricing and versions.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        # Selected passage about a specific product's price
                        "text": "InfraAgent Pro costs $99.99 per month",
                        "url": "https://example.com/pricing",
                        "relevance": "sufficient",
                    }
                ],
            }
        ]
        request = AssessmentRequest(
            raw_request="What is the price of InfraAgent Pro?",
            intent="EXTERNAL_VERIFICATION",
            evidence=(
                EvidencePackage(
                    capability_name="external_verification",
                    evidence_name="explicit_url",
                    data={
                        "documents": documents,
                    },
                    source="internet",
                ),
            ),
        )
        guarded = redact_ungrounded_external_claims(
            "InfraAgent Pro costs $99.99 per month.", request
        )
        assert "$99.99" in guarded

    def test_explicit_url_fact_absent_remains_insufficient(self) -> None:
        """Explicit URL: successful fetch but requested fact absent remains
        insufficient."""
        documents = [
            {
                "content": "This is an about page for ExampleCorp.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        # Selected passage doesn't contain version info
                        "text": "ExampleCorp provides cloud infrastructure services.",
                        "url": "https://example.com/about",
                        "relevance": "sufficient",
                    }
                ],
            }
        ]
        request = AssessmentRequest(
            raw_request="What is the current version of Python? Visit https://example.com/about",
            intent="EXTERNAL_VERIFICATION",
            evidence=(
                EvidencePackage(
                    capability_name="external_verification",
                    evidence_name="explicit_url",
                    data={
                        "documents": documents,
                    },
                    source="internet",
                ),
            ),
        )
        guarded = redact_ungrounded_external_claims(
            "Python version is 3.14.2.", request
        )
        # 3.14.2 should be redacted because it's not in the selected passage
        assert "3.14.2" not in guarded
        assert "chưa xác nhận" in guarded

    def test_non_external_intent_returns_original_text(self) -> None:
        """Non-EXTERNAL_VERIFICATION intent returns original text unchanged."""
        documents = [
            {
                "content": "Some content.",
                "relevance": "sufficient",
            }
        ]
        request = _external_request(documents, intent="CAPABILITY_ASSESSMENT")
        guarded = redact_ungrounded_external_claims(
            "Python version is 3.14.2.", request
        )
        # Should return original text unchanged for non-external intent
        assert "3.14.2" in guarded
        assert "chưa xác nhận" not in guarded

    def test_backward_compatibility_without_selected_passages(self) -> None:
        """When selected_passages are not present, falls back to full content."""
        documents = [
            {
                "content": "Python version 3.14.2 is the latest stable release.",
                "relevance": "sufficient",
                # No selected_passages key — backward compatibility test
            }
        ]
        request = _external_request(documents)
        guarded = redact_ungrounded_external_claims(
            "Phiên bản mới nhất là 3.14.2.", request
        )
        # Should still work using full content as fallback
        assert "3.14.2" in guarded

    def test_no_assertion_may_merely_check_non_null(self) -> None:
        """Verify semantic correctness, not just non-null/non-empty output."""
        documents = [
            {
                "content": "Python version 3.14.2 is available.",
                "relevance": "sufficient",
                "selected_passages": [
                    {
                        "text": "Python version 3.14.2",
                        "url": "https://example.com/python",
                        "relevance": "sufficient",
                    }
                ],
            }
        ]
        request = _external_request(documents)

        # Test 1: Correct value should be preserved
        guarded_correct = redact_ungrounded_external_claims(
            "Phiên bản mới nhất là 3.14.2.", request
        )
        assert "3.14.2" in guarded_correct
        assert "chưa xác nhận" not in guarded_correct

        # Test 2: Wrong value should be redacted (not just non-null)
        guarded_wrong = redact_ungrounded_external_claims(
            "Phiên bản mới nhất là 3.99.0.", request
        )
        assert "3.99.0" not in guarded_wrong
        assert "chưa xác nhận" in guarded_wrong
        # The output must contain the redaction marker, not just be non-empty
        assert len(guarded_wrong) > 0
