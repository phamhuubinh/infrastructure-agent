"""Tests for ExternalVerificationExecutor with relevance + failure handling.

This file preserves ALL 7 legacy tests from HEAD plus new SUFFICIENT/PARTIAL
relevance tests added during GA2-R1.

LEGACY TESTS (from HEAD):
1. test_search_select_fetch_normalizes_fresh_external_evidence
2. test_explicit_url_fetches_directly_without_search
3. test_fetch_success_with_empty_content_is_not_verified_evidence
4. test_unavailable_search_never_turns_into_model_or_fetch_evidence
5. test_failed_fetch_is_not_cached_as_valid_evidence
6. test_page_fetch_budget_and_byte_limit_are_propagated
7. test_explicit_private_url_still_hits_the_shared_ssrf_boundary

NEW TESTS (GA2-R1):
8. TestSufficientWithFailures.test_sufficient_with_fetch_failure
9. TestSufficientWithFailures.test_partial_with_fetch_failure
10. TestSufficientWithFailures.test_multiple_sufficient_no_failure
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.external_verification import (
    ExternalEvidenceCache,
    ExternalEvidenceRelevance,
    ExternalRequestBudget,
    ExternalVerificationExecutor,
)
from src.pipeline.request_frame import RequestFrame
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from src.tool.internet_tool import InternetTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry

# ===========================================================================
# LEGACY FIXTURE — preserved from HEAD
# ===========================================================================


class _InternetKnowledgeTool:
    """Legacy mock tool from HEAD test_external_verification.py."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.search_data: dict[str, object] = {
            "status": "ok",
            "provider": "fixture-search",
            "results": [
                {"title": "Official", "url": "https://official.example/release"},
                {"title": "Mirror", "url": "https://official.example/release#same"},
                {"title": "Independent", "url": "https://other.example/news"},
            ],
        }
        self.fetch_payloads: dict[str, dict[str, object]] = {
            "https://official.example/release": {
                "url": "https://official.example/release",
                "status": 200,
                "content_type": "text/html",
                "content_length": 30,
                "truncated": False,
                "data": "Python current version is 3.14.2",
            },
            "https://other.example/news": {
                "url": "https://other.example/news",
                "status": 200,
                "content_type": "text/html",
                "content_length": 25,
                "truncated": False,
                "data": "Independent corroboration of Python 3.14.2 release",
            },
        }

    def source_names(self) -> tuple[str, ...]:
        return ("internet",)

    def source_kind(self, source: str) -> str:
        assert source == "internet"
        return "internet"

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        self.calls.append(dict(arguments))
        if arguments["resource"] == "web_search":
            return ToolResult(success=True, data=self.search_data)
        url = str(arguments["url"])
        payload = self.fetch_payloads.get(url)
        if payload is None:
            return ToolResult(success=False, error=f"blocked or unavailable: {url}")
        return ToolResult(success=True, data=payload)


def _legacy_frame(question: str):
    """Legacy frame builder using Normalizer."""
    from src.pipeline.normalizer import Normalizer

    return Normalizer().normalize(question)


# ===========================================================================
# NEW TEST FIXTURE — for SUFFICIENT/PARTIAL/IRRELEVANT tests
# ===========================================================================


class _MockKnowledgeTool:
    """Mock tool that returns configurable search and fetch results."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.search_data: dict[str, object] = {
            "status": "ok",
            "provider": "mock-search",
            "results": [],
        }
        self.fetch_payloads: dict[str, dict[str, object]] = {}

    def source_names(self) -> tuple[str, ...]:
        return ("internet",)

    def source_kind(self, source: str) -> str:
        assert source == "internet"
        return "internet"

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        self.calls.append(dict(arguments))
        if arguments["resource"] == "web_search":
            return ToolResult(success=True, data=self.search_data)
        url = str(arguments["url"])
        payload = self.fetch_payloads.get(url)
        if payload is None:
            return ToolResult(success=False, error=f"URL not found: {url}")
        return ToolResult(success=True, data=payload)


def _frame(query: str) -> RequestFrame:
    """Create a request frame for the given query."""
    return RequestFrame(
        raw_request=query,
        concepts=(),
        operation="inspect",
        target_raw=None,
        target_resolved=None,
        parameters=None,
        answer_type=None,
        timeframe=None,
        confidence=0.0,
        ambiguity=(),
        lexical_tokens=(),
        matched_synonyms=(),
        concept_candidates=(),
        intent_candidates=(),
        target_candidates=(),
        routing_status=None,
        context_applied=(),
        context_snapshot={},
        subframes=(),
        request_domain=None,  # type: ignore[arg-type]
        information_scope=None,  # type: ignore[arg-type]
        external_need=None,  # type: ignore[arg-type]
        source_constraints=(),
    )


# ===========================================================================
# LEGACY TESTS (from HEAD) — preserved
# ===========================================================================


def test_search_select_fetch_normalizes_fresh_external_evidence() -> None:
    """LEGACY: Search selects and fetches normalized fresh external evidence."""
    tool = _InternetKnowledgeTool()
    executor = ExternalVerificationExecutor(
        tool,  # type: ignore[arg-type]
        now=lambda: datetime(2026, 8, 8, tzinfo=timezone.utc),
    )

    outcome = executor.collect(
        _legacy_frame("What is the current Python version?"),
        "What is the current Python version?",
    )

    assert outcome.verified is True
    assert outcome.search_calls == 1
    assert outcome.fetch_calls == 2
    assert len(outcome.documents) == 2
    assert outcome.evidence is not None
    assert outcome.evidence.source_tool == "internet"
    assert len(outcome.evidence.facts) >= 2
    assert all(fact.source == "internet" for fact in outcome.evidence.facts)
    assert all(fact.provenance.source_reference for fact in outcome.evidence.facts)
    # Same URL with a fragment is deduplicated, while a second domain is kept.
    assert [call["resource"] for call in tool.calls] == [
        "web_search",
        "web_fetch",
        "web_fetch",
    ]


def test_explicit_url_fetches_directly_without_search() -> None:
    """LEGACY: Explicit URL fetches directly without search."""
    tool = _InternetKnowledgeTool()
    tool.fetch_payloads = {
        "https://official.example/release": {
            "url": "https://official.example/release",
            "status": 200,
            "content_type": "text/html",
            "content_length": 30,
            "truncated": False,
            "data": "Python current version is 3.14.2",
        }
    }
    outcome = ExternalVerificationExecutor(tool).collect(  # type: ignore[arg-type]
        _legacy_frame("Read https://official.example/release for current version"),
        "Read https://official.example/release for current version",
    )

    assert outcome.verified is True
    assert outcome.search_calls == 0
    assert outcome.fetch_calls == 1
    assert [call["resource"] for call in tool.calls] == ["web_fetch"]


def test_fetch_success_with_empty_content_is_not_verified_evidence() -> None:
    """LEGACY: Fetch success with empty content is NOT verified evidence."""
    tool = _InternetKnowledgeTool()
    tool.fetch_payloads = {
        "https://official.example/release": {
            "url": "https://official.example/release",
            "status": 200,
            "fetch_status": "FETCH_SUCCESS",
            "content_status": "CONTENT_EMPTY",
            "content_type": "text/html",
            "content_length": 0,
            "truncated": False,
            "data": "",
        }
    }

    outcome = ExternalVerificationExecutor(tool).collect(  # type: ignore[arg-type]
        _legacy_frame("Đọc https://official.example/release"),
        "Đọc https://official.example/release",
    )

    assert outcome.verified is False
    assert "CONTENT_EMPTY" in outcome.failures[0]


def test_unavailable_search_never_turns_into_model_or_fetch_evidence() -> None:
    """LEGACY: Unavailable search never turns into model or fetch evidence."""
    tool = _InternetKnowledgeTool()
    tool.search_data = {}

    def failing_execute(arguments: dict[str, object]) -> ToolResult:
        tool.calls.append(dict(arguments))
        return ToolResult(success=False, error="Search provider is not configured.")

    tool.execute = failing_execute  # type: ignore[method-assign]
    outcome = ExternalVerificationExecutor(tool).collect(  # type: ignore[arg-type]
        _legacy_frame("Giá Bitcoin hiện tại khoảng bao nhiêu?"),
        "Giá Bitcoin hiện tại khoảng bao nhiêu?",
    )

    assert outcome.verified is False
    assert "not configured" in outcome.failures[0].lower()
    assert outcome.fetch_calls == 0


def test_failed_fetch_is_not_cached_as_valid_evidence() -> None:
    """LEGACY: Failed fetch is not cached as valid evidence."""
    tool = _InternetKnowledgeTool()
    tool.fetch_payloads = {}
    cache = ExternalEvidenceCache()
    executor = ExternalVerificationExecutor(
        tool,  # type: ignore[arg-type]
        cache=cache,
        budget=ExternalRequestBudget(max_page_fetches=1),
    )
    frame = _legacy_frame("Phiên bản Python stable mới nhất hiện tại là gì?")

    first = executor.collect(frame, frame.raw_request)
    second = executor.collect(frame, frame.raw_request)

    assert first.verified is False
    assert second.verified is False
    # Search can be cached, but each failed page fetch is executed again.
    assert [call["resource"] for call in tool.calls].count("web_fetch") == 2


def test_page_fetch_budget_and_byte_limit_are_propagated() -> None:
    """LEGACY: Page fetch budget and byte limit are propagated."""
    tool = _InternetKnowledgeTool()
    executor = ExternalVerificationExecutor(
        tool,  # type: ignore[arg-type]
        budget=ExternalRequestBudget(max_page_fetches=1, max_total_bytes=100),
    )

    outcome = executor.collect(
        _legacy_frame("Phiên bản Python stable mới nhất hiện tại là gì?"),
        "Phiên bản Python stable mới nhất hiện tại là gì?",
    )

    fetch = next(call for call in tool.calls if call["resource"] == "web_fetch")
    assert outcome.fetch_calls == 1
    assert fetch["max_bytes"] == 100


def test_explicit_private_url_still_hits_the_shared_ssrf_boundary() -> None:
    """LEGACY: Explicit private URL still hits the shared SSRF boundary."""
    registry = TargetRegistry()
    registry.register_tool("internet", InternetTool())
    executor = ExternalVerificationExecutor(KnowledgeTool(registry))

    outcome = executor.collect(
        _legacy_frame("Đọc http://169.254.169.254/latest/meta-data/"),
        "Đọc http://169.254.169.254/latest/meta-data/",
    )

    assert outcome.verified is False
    assert "private address" in outcome.failures[0].lower()


def test_v2_current_action_uses_exact_source_and_requires_fetched_evidence() -> None:
    tool = _InternetKnowledgeTool()
    executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]

    outcome = executor.collect_current_action(
        source_id="internet",
        query="current Python version",
        user_request="What is the current Python version?",
        freshness_required=True,
    )

    assert outcome.verified is True
    assert outcome.search_calls == 1
    assert outcome.fetch_calls >= 1
    assert [call["resource"] for call in tool.calls][0] == "web_search"
    evidence = executor.action_evidence(outcome)
    assert evidence.capability_status is CapabilityStatus.VALID
    assert any(
        fact.metric == "external.document.supporting_passage" for fact in evidence.facts
    )


def test_v2_url_action_fetches_exact_url_without_search() -> None:
    url = "https://official.example/release"
    tool = _InternetKnowledgeTool()
    tool.fetch_payloads = {
        url: {
            "url": "https://public-final.example/release",
            "status": 200,
            "content_type": "text/html",
            "content_length": 30,
            "truncated": False,
            "data": "Python current version is 3.14.2",
        }
    }
    executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]

    outcome = executor.collect_url_action(
        source_id="internet",
        url=url,
        user_request="Read this URL for the current Python version.",
        freshness_required=True,
    )

    assert outcome.verified is True
    assert [call["resource"] for call in tool.calls] == ["web_fetch"]
    assert tool.calls[0]["url"] == url
    evidence = executor.action_evidence(outcome)
    assert evidence.capability_status is CapabilityStatus.VALID
    assert all(fact.provenance.source_reference == url for fact in evidence.facts)


# ===========================================================================
# NEW TESTS (GA2-R1) — SUFFICIENT/PARTIAL/IRRELEVANT relevance
# ===========================================================================


class TestSufficientWithFailures:
    """Test that SUFFICIENT + fetch failure = verified=True, partial=True."""

    def test_sufficient_with_fetch_failure(self) -> None:
        """A SUFFICIENT document AND a fetch failure should yield verified=True, partial=True.

        Contract:
        - outcome.verified is True (SUFFICIENT document present)
        - outcome.partial is True (has failures despite having usable evidence)
        - failures are preserved
        - relevant/sufficient document is preserved
        """
        tool = _MockKnowledgeTool()
        # Search returns two URLs
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [
                {"title": "Good Page", "url": "https://example.com/good"},
                {"title": "Bad Page", "url": "https://example.com/bad"},
            ],
        }
        # Good page has SUFFICIENT content for "version" request
        tool.fetch_payloads = {
            "https://example.com/good": {
                "url": "https://example.com/good",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "Version 3.12.0 is the latest stable release",
            },
            "https://example.com/bad": {
                "url": "https://example.com/bad",
                "status": 500,
                "content_type": "text/html",
                "content_length": 0,
                "truncated": False,
                "error": "HTTP 500",
            },
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version?"),
            "What is the current version?",
        )

        # Contract assertions
        assert outcome.verified is True, "SUFFICIENT document present"
        assert outcome.partial is True, "Has failures despite SUFFICIENT evidence"
        assert len(outcome.failures) > 0, "Failures preserved"
        assert len(outcome.documents) == 1, "Only successful document preserved"
        assert outcome.documents[0].relevance == ExternalEvidenceRelevance.SUFFICIENT
        assert outcome.documents[0].url == "https://example.com/good"

    def test_partial_with_fetch_failure(self) -> None:
        """PARTIAL document + fetch failure should yield verified=False, partial=True."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [
                {"title": "Partial Page", "url": "https://example.com/partial"},
                {"title": "Bad Page", "url": "https://example.com/bad"},
            ],
        }
        # Partial page has PARTIAL content (truncated, single keyword)
        tool.fetch_payloads = {
            "https://example.com/partial": {
                "url": "https://example.com/partial",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": True,
                "data": "Version 3.",
            },
            "https://example.com/bad": {
                "url": "https://example.com/bad",
                "status": 500,
                "content_type": "text/html",
                "content_length": 0,
                "truncated": False,
                "error": "HTTP 500",
            },
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version?"),
            "What is the current version?",
        )

        # verified=False (no SUFFICIENT document)
        assert outcome.verified is False
        # partial=True (PARTIAL document + failures)
        assert outcome.partial is True
        # Failures preserved
        assert len(outcome.failures) > 0
        # Only successful document preserved
        assert len(outcome.documents) == 1
        assert outcome.documents[0].relevance == ExternalEvidenceRelevance.PARTIAL

    def test_multiple_sufficient_no_failure(self) -> None:
        """Multiple SUFFICIENT documents with no failures should yield verified=True, partial=False."""
        tool = _MockKnowledgeTool()
        tool.search_data = {
            "status": "ok",
            "provider": "mock-search",
            "results": [
                {"title": "Page 1", "url": "https://example.com/page1"},
                {"title": "Page 2", "url": "https://example.com/page2"},
            ],
        }
        tool.fetch_payloads = {
            "https://example.com/page1": {
                "url": "https://example.com/page1",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "Version 3.12.0 is the latest stable release",
            },
            "https://example.com/page2": {
                "url": "https://example.com/page2",
                "status": 200,
                "content_type": "text/html",
                "content_length": 100,
                "truncated": False,
                "data": "The current version is 3.12.0",
            },
        }
        executor = ExternalVerificationExecutor(tool)  # type: ignore[arg-type]
        outcome = executor.collect(
            _frame("What is the current version?"),
            "What is the current version?",
        )

        assert outcome.verified is True
        assert outcome.partial is False
        assert len(outcome.failures) == 0
        assert len(outcome.documents) == 2
        assert all(
            doc.relevance == ExternalEvidenceRelevance.SUFFICIENT
            for doc in outcome.documents
        )
