from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.external_verification import (
    ExternalEvidenceCache,
    ExternalRequestBudget,
    ExternalVerificationExecutor,
)
from src.pipeline.normalizer import Normalizer
from src.shared.execution.tool_result import ToolResult
from src.tool.internet_tool import InternetTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry


class _InternetKnowledgeTool:
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
                "data": "Official release content",
            },
            "https://other.example/news": {
                "url": "https://other.example/news",
                "status": 200,
                "content_type": "text/html",
                "content_length": 25,
                "truncated": False,
                "data": "Independent corroboration",
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


def _frame(question: str):
    return Normalizer().normalize(question)


def test_search_select_fetch_normalizes_fresh_external_evidence() -> None:
    tool = _InternetKnowledgeTool()
    executor = ExternalVerificationExecutor(
        tool,  # type: ignore[arg-type]
        now=lambda: datetime(2026, 8, 8, tzinfo=timezone.utc),
    )

    outcome = executor.collect(
        _frame("Phiên bản Python stable mới nhất hiện tại là gì?"),
        "Phiên bản Python stable mới nhất hiện tại là gì?",
    )

    assert outcome.verified is True
    assert outcome.search_calls == 1
    assert outcome.fetch_calls == 2
    assert len(outcome.documents) == 2
    assert outcome.evidence is not None
    assert outcome.evidence.source_tool == "internet"
    assert len(outcome.evidence.facts) == 2
    assert all(fact.source == "internet" for fact in outcome.evidence.facts)
    assert all(fact.provenance.source_reference for fact in outcome.evidence.facts)
    # Same URL with a fragment is deduplicated, while a second domain is kept.
    assert [call["resource"] for call in tool.calls] == [
        "web_search",
        "web_fetch",
        "web_fetch",
    ]


def test_explicit_url_fetches_directly_without_search() -> None:
    tool = _InternetKnowledgeTool()
    tool.fetch_payloads = {
        "https://official.example/release": {
            "url": "https://official.example/release",
            "status": 200,
            "content_type": "text/html",
            "content_length": 30,
            "truncated": False,
            "data": "Official release content",
        }
    }
    outcome = ExternalVerificationExecutor(tool).collect(  # type: ignore[arg-type]
        _frame("Đọc https://official.example/release"),
        "Đọc https://official.example/release",
    )

    assert outcome.verified is True
    assert outcome.search_calls == 0
    assert outcome.fetch_calls == 1
    assert [call["resource"] for call in tool.calls] == ["web_fetch"]


def test_fetch_success_with_empty_content_is_not_verified_evidence() -> None:
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
        _frame("Đọc https://official.example/release"),
        "Đọc https://official.example/release",
    )

    assert outcome.verified is False
    assert "CONTENT_EMPTY" in outcome.failures[0]


def test_unavailable_search_never_turns_into_model_or_fetch_evidence() -> None:
    tool = _InternetKnowledgeTool()
    tool.search_data = {}
    # Return a typed tool failure instead of a payload.
    def failing_execute(arguments: dict[str, object]) -> ToolResult:
        tool.calls.append(dict(arguments))
        return ToolResult(success=False, error="Search provider is not configured.")

    tool.execute = failing_execute  # type: ignore[method-assign]
    outcome = ExternalVerificationExecutor(tool).collect(  # type: ignore[arg-type]
        _frame("Giá Bitcoin hiện tại khoảng bao nhiêu?"),
        "Giá Bitcoin hiện tại khoảng bao nhiêu?",
    )

    assert outcome.verified is False
    assert "not configured" in outcome.failures[0].lower()
    assert outcome.fetch_calls == 0


def test_failed_fetch_is_not_cached_as_valid_evidence() -> None:
    tool = _InternetKnowledgeTool()
    tool.fetch_payloads = {}
    cache = ExternalEvidenceCache()
    executor = ExternalVerificationExecutor(
        tool,  # type: ignore[arg-type]
        cache=cache,
        budget=ExternalRequestBudget(max_page_fetches=1),
    )
    frame = _frame("Phiên bản Python stable mới nhất hiện tại là gì?")

    first = executor.collect(frame, frame.raw_request)
    second = executor.collect(frame, frame.raw_request)

    assert first.verified is False
    assert second.verified is False
    # Search can be cached, but each failed page fetch is executed again.
    assert [call["resource"] for call in tool.calls].count("web_fetch") == 2


def test_page_fetch_budget_and_byte_limit_are_propagated() -> None:
    tool = _InternetKnowledgeTool()
    executor = ExternalVerificationExecutor(
        tool,  # type: ignore[arg-type]
        budget=ExternalRequestBudget(max_page_fetches=1, max_total_bytes=100),
    )

    outcome = executor.collect(
        _frame("Phiên bản Python stable mới nhất hiện tại là gì?"),
        "Phiên bản Python stable mới nhất hiện tại là gì?",
    )

    fetch = next(call for call in tool.calls if call["resource"] == "web_fetch")
    assert outcome.fetch_calls == 1
    assert fetch["max_bytes"] == 100


def test_explicit_private_url_still_hits_the_shared_ssrf_boundary() -> None:
    registry = TargetRegistry()
    registry.register_tool("internet", InternetTool())
    executor = ExternalVerificationExecutor(KnowledgeTool(registry))

    outcome = executor.collect(
        _frame("Đọc http://169.254.169.254/latest/meta-data/"),
        "Đọc http://169.254.169.254/latest/meta-data/",
    )

    assert outcome.verified is False
    assert "private address" in outcome.failures[0].lower()
