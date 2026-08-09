"""GA2-R1-B: claim validator filters by relevance for external verification.

Tests that redact_ungrounded_external_claims only grounds concrete claims
(version, date, price, identity) against documents with relevance == "sufficient".
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.model.claim_validator import redact_ungrounded_external_claims
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage


def _external_evidence(
    documents: list[dict[str, object]],
) -> tuple[EvidencePackage, ...]:
    """Create an EXTERNAL_VERIFICATION evidence package with documents."""
    return (
        EvidencePackage(
            capability_name="external_verification",
            evidence_name="external_current",
            data={
                "query": "What is the current version?",
                "provider": "mock-search",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "documents": documents,
            },
            source_tool="internet",
            source="internet",
            resource="web_fetch",
            parameters=(
                ("provider", "mock-search"),
                ("query", "What is the current version?"),
            ),
        ),
    )


class TestExternalClaimGroundingByRelevance:
    """Test that claim grounding only uses SUFFICIENT relevance documents."""

    def test_sufficient_document_grounds_version_claim(self) -> None:
        """SUFFICIENT document content should NOT be redacted."""
        evidence = _external_evidence(
            [
                {
                    "title": "Release",
                    "url": "https://example.com/release",
                    "content": "Version 3.12.0 is the latest stable release",
                    "provider": "mock-search",
                    "relevance": "sufficient",
                    "content_status": "CONTENT_EXTRACTED",
                }
            ]
        )
        request = AssessmentRequest(
            raw_request="What is the current version?",
            intent="EXTERNAL_VERIFICATION",
            evidence=evidence,
            facts=(),
        )
        # Version 3.12.0 is in SUFFICIENT document => NOT redacted
        response = "The current version is 3.12.0"
        redacted = redact_ungrounded_external_claims(response, request, lang="en")
        assert "3.12.0" in redacted

    def test_partial_document_does_not_ground_version_claim(self) -> None:
        """PARTIAL document content is filtered out => no SUFFICIENT corpus.

        When only PARTIAL documents exist (no SUFFICIENT), the corpus is empty
        and the function returns the "Could not determine" fallback message.
        """
        evidence = _external_evidence(
            [
                {
                    "title": "Partial",
                    "url": "https://example.com/partial",
                    "content": "Version 3.",
                    "provider": "mock-search",
                    "relevance": "partial",
                    "content_status": "CONTENT_TRUNCATED",
                }
            ]
        )
        request = AssessmentRequest(
            raw_request="What is the current version?",
            intent="EXTERNAL_VERIFICATION",
            evidence=evidence,
            facts=(),
        )
        # No SUFFICIENT documents => corpus empty => "Could not determine"
        response = "The current version is 3.12.0"
        redacted = redact_ungrounded_external_claims(response, request, lang="en")
        assert "Could not determine this from the fetched content." in redacted
        assert "3.12.0" not in redacted

    def test_irrelevant_document_does_not_ground_version_claim(self) -> None:
        """IRRELEVANT document content is filtered out => no SUFFICIENT corpus.

        When only IRRELEVANT documents exist (no SUFFICIENT), the corpus is empty
        and the function returns the "Could not determine" fallback message.
        """
        evidence = _external_evidence(
            [
                {
                    "title": "Weather",
                    "url": "https://example.com/weather",
                    "content": "Sunny skies ahead",
                    "provider": "mock-search",
                    "relevance": "irrelevant",
                    "content_status": "CONTENT_EXTRACTED",
                }
            ]
        )
        request = AssessmentRequest(
            raw_request="What is the current version?",
            intent="EXTERNAL_VERIFICATION",
            evidence=evidence,
            facts=(),
        )
        # No SUFFICIENT documents => corpus empty => "Could not determine"
        response = "The current version is 3.12.0"
        redacted = redact_ungrounded_external_claims(response, request, lang="en")
        assert "Could not determine this from the fetched content." in redacted

    def test_mixed_relevance_uses_only_sufficient(self) -> None:
        """When multiple documents exist, only SUFFICIENT grounds claims."""
        evidence = _external_evidence(
            [
                {
                    "title": "Partial",
                    "url": "https://example.com/partial",
                    "content": "Version 3.12.0",
                    "provider": "mock-search",
                    "relevance": "partial",
                    "content_status": "CONTENT_TRUNCATED",
                },
                {
                    "title": "Irrelevant",
                    "url": "https://example.com/irrelevant",
                    "content": "Weather forecast",
                    "provider": "mock-search",
                    "relevance": "irrelevant",
                    "content_status": "CONTENT_EXTRACTED",
                },
                {
                    "title": "Sufficient",
                    "url": "https://example.com/sufficient",
                    "content": "Python version 3.12.0 is the latest stable release",
                    "provider": "mock-search",
                    "relevance": "sufficient",
                    "content_status": "CONTENT_EXTRACTED",
                },
            ]
        )
        request = AssessmentRequest(
            raw_request="What is the current version of Python?",
            intent="EXTERNAL_VERIFICATION",
            evidence=evidence,
            facts=(),
        )
        # Version 3.12.0 is in SUFFICIENT document => NOT redacted
        response = "The current Python version is 3.12.0"
        redacted = redact_ungrounded_external_claims(response, request, lang="en")
        assert "3.12.0" in redacted

    def test_no_sufficient_documents_returns_not_determined(self) -> None:
        """When no SUFFICIENT documents exist, returns "Could not determine"."""
        evidence = _external_evidence(
            [
                {
                    "title": "Partial",
                    "url": "https://example.com/partial",
                    "content": "Version 3.12.0",
                    "provider": "mock-search",
                    "relevance": "partial",
                    "content_status": "CONTENT_TRUNCATED",
                }
            ]
        )
        request = AssessmentRequest(
            raw_request="What is the current version?",
            intent="EXTERNAL_VERIFICATION",
            evidence=evidence,
            facts=(),
        )
        # No SUFFICIENT documents => corpus empty => "Could not determine"
        response = "The current version is 3.12.0"
        redacted = redact_ungrounded_external_claims(response, request, lang="en")
        assert "Could not determine this from the fetched content." in redacted

    def test_non_external_intent_unchanged(self) -> None:
        """Non-EXTERNAL_VERIFICATION intent should not be affected."""
        evidence = _external_evidence(
            [
                {
                    "title": "Partial",
                    "url": "https://example.com/partial",
                    "content": "Version 3.12.0",
                    "provider": "mock-search",
                    "relevance": "partial",
                    "content_status": "CONTENT_TRUNCATED",
                }
            ]
        )
        request = AssessmentRequest(
            raw_request="What is the current version?",
            intent="NORMAL_ASSESSMENT",  # Not EXTERNAL_VERIFICATION
            evidence=evidence,
            facts=(),
        )
        response = "The current version is 3.12.0"
        redacted = redact_ungrounded_external_claims(response, request, lang="en")
        # Should be unchanged (not redacted)
        assert redacted == response

    def test_sufficient_date_grounds_date_claim(self) -> None:
        """SUFFICIENT document with date should NOT be redacted."""
        evidence = _external_evidence(
            [
                {
                    "title": "Release",
                    "url": "https://example.com/release",
                    "content": "Release date is 2024-08-15",
                    "provider": "mock-search",
                    "relevance": "sufficient",
                    "content_status": "CONTENT_EXTRACTED",
                }
            ]
        )
        request = AssessmentRequest(
            raw_request="What is the release date?",
            intent="EXTERNAL_VERIFICATION",
            evidence=evidence,
            facts=(),
        )
        response = "The release date is 2024-08-15"
        redacted = redact_ungrounded_external_claims(response, request, lang="en")
        assert "2024-08-15" in redacted

    def test_sufficient_price_grounds_price_claim(self) -> None:
        """SUFFICIENT document with price should NOT be redacted."""
        evidence = _external_evidence(
            [
                {
                    "title": "Pricing",
                    "url": "https://example.com/pricing",
                    "content": "Price is $99.99 per month",
                    "provider": "mock-search",
                    "relevance": "sufficient",
                    "content_status": "CONTENT_EXTRACTED",
                }
            ]
        )
        request = AssessmentRequest(
            raw_request="What is the price?",
            intent="EXTERNAL_VERIFICATION",
            evidence=evidence,
            facts=(),
        )
        response = "The price is $99.99 per month"
        redacted = redact_ungrounded_external_claims(response, request, lang="en")
        assert "$99.99" in redacted
