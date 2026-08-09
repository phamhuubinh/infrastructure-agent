"""GA2-F10: deterministic external failure matrix."""

from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.external_verification import (
    ExternalContentStatus,
    ExternalEvidenceRelevance,
    ExternalVerificationExecutor,
)
from src.pipeline.request_frame import RequestFrame
from src.pipeline.request_semantics import (
    ExternalNeed,
    InformationScope,
    RequestDomain,
)
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus


class _FakeKnowledgeTool:
    """Minimal knowledge_tool stand-in yielding controlled failures."""

    def __init__(self, fetch_payload: dict[str, object] | None = None):
        self._fetch_payload = fetch_payload

    def source_names(self) -> list[str]:
        return ["internet"]

    def source_kind(self, name: str) -> str:
        return "internet"

    def source_provider_identity(self, source: str) -> str:
        return "fake-provider"

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        if arguments.get("resource") == "web_fetch":
            if self._fetch_payload is None:
                return ToolResult(success=False, error="network failure")
            return ToolResult(
                success=True,
                data=self._fetch_payload,
                capability_status=CapabilityStatus.VALID,
            )
        return ToolResult(
            success=True,
            data={
                "status": "ok",
                "provider": "fake-provider",
                "results": [{"title": "x", "url": "https://example.com/page"}],
            },
        )


def _frame(explicit_url: str) -> RequestFrame:
    return RequestFrame(
        raw_request="kiểm tra thông tin hiện tại",
        concepts=("noise",),
        request_domain=RequestDomain.EXTERNAL_INFORMATION,
        information_scope=InformationScope.CURRENT_EXTERNAL,
        external_need=ExternalNeed.REQUIRED,
        explicit_url=explicit_url,
    )


def _executor(payload: dict[str, object] | None) -> ExternalVerificationExecutor:
    return ExternalVerificationExecutor(
        _FakeKnowledgeTool(payload),  # type: ignore[arg-type]
        now=lambda: datetime(2026, 8, 8, tzinfo=timezone.utc),
        enabled=True,
    )


def _payload(content_status: str, **extra: object) -> dict[str, object]:
    data: dict[str, object] = {
        "url": "https://example.com/page",
        "content_status": content_status,
        "data": "nội dung",
        "content_type": "text/html",
        "content_length": 100,
        "truncated": False,
    }
    data.update(extra)
    return data


def test_unsupported_content_type_never_sufficient() -> None:
    executor = _executor(
        _payload(
            ExternalContentStatus.CONTENT_UNSUPPORTED.value,
            data=None,
            content_type="application/octet-stream",
            content_length=0,
        )
    )
    outcome = executor.collect(_frame("https://example.com/x"), "q")
    assert outcome.verified is False
    assert outcome.evidence is None
    assert outcome.failures


def test_empty_body_never_sufficient() -> None:
    executor = _executor(
        _payload(ExternalContentStatus.CONTENT_EMPTY.value, data="", content_length=0)
    )
    outcome = executor.collect(_frame("https://example.com/x"), "q")
    assert outcome.verified is False


def test_http_404_never_sufficient() -> None:
    executor = _executor({"error": "HTTP 404", "url": "https://example.com/missing"})
    outcome = executor.collect(_frame("https://example.com/missing"), "q")
    assert outcome.verified is False


def test_http_500_never_sufficient() -> None:
    executor = _executor({"error": "HTTP 500", "url": "https://example.com/debug"})
    outcome = executor.collect(_frame("https://example.com/debug"), "q")
    assert outcome.verified is False


def test_dns_failure_never_sufficient() -> None:
    executor = _executor(None)
    outcome = executor.collect(_frame("https://unknown.invalid/x"), "q")
    assert outcome.verified is False


def test_oversized_body_is_truncated_partial() -> None:
    """Truncated content with version keyword is PARTIAL relevance (verified=False)."""
    # Request has "version" keyword, content has "Version 3." which is truncated
    # Single keyword + truncated = PARTIAL relevance, not SUFFICIENT
    executor = _executor(
        {
            "url": "https://example.com/page",
            "content_status": ExternalContentStatus.CONTENT_TRUNCATED.value,
            "data": "Version 3.",
            "content_type": "text/html",
            "content_length": 100,
            "truncated": True,
        }
    )
    outcome = executor.collect(_frame("https://example.com/big"), "current version")
    # PARTIAL relevance = verified=False, partial=True
    assert outcome.verified is False
    assert outcome.partial is True
    assert outcome.documents[0].relevance == ExternalEvidenceRelevance.PARTIAL
    assert outcome.has_relevant_evidence is True
    assert all(
        doc.content_status is ExternalContentStatus.CONTENT_TRUNCATED
        for doc in outcome.documents
    )
