from __future__ import annotations

from src.pipeline.external_verification import (
    ExternalVerificationExecutor,
)
from src.shared.execution.tool_result import (
    ToolResult,
)
from src.tool.capability_result import (
    CapabilityStatus,
)


class FakeInternetTool:
    def __init__(self) -> None:
        self.calls: list[
            dict[str, object]
        ] = []

        self.search_data = {
            "status": "ok",
            "provider": "fixture",
            "results": [
                {
                    "title": "Official",
                    "url": (
                        "https://example.com/"
                        "release"
                    ),
                }
            ],
        }

        self.fetch_payloads = {
            "https://example.com/release": {
                "url": (
                    "https://example.com/"
                    "release"
                ),
                "status": 200,
                "content_type": "text/html",
                "content_length": 30,
                "truncated": False,
                "data": (
                    "Python current version "
                    "is 3.14.2"
                ),
            }
        }

    def source_names(
        self,
    ) -> tuple[str, ...]:
        return ("internet",)

    def source_kind(
        self,
        source: str,
    ) -> str:
        assert source == "internet"
        return "internet"

    def execute(
        self,
        arguments: dict[str, object],
    ) -> ToolResult:
        self.calls.append(
            dict(arguments)
        )

        if (
            arguments["resource"]
            == "web_search"
        ):
            return ToolResult(
                success=True,
                data=self.search_data,
            )

        url = str(arguments["url"])
        payload = self.fetch_payloads.get(
            url
        )

        if payload is None:
            return ToolResult(
                success=False,
                error="unavailable",
            )

        return ToolResult(
            success=True,
            data=payload,
        )


def test_search_action_returns_discovery_evidence() -> None:
    tool = FakeInternetTool()
    executor = (
        ExternalVerificationExecutor(
            tool  # type: ignore[arg-type]
        )
    )

    outcome = executor.collect_search_action(
        source_id="internet",
        queries=("current Python version",),
        max_results=5,
        freshness_required=True,
    )

    assert outcome.search_calls == 1
    assert outcome.fetch_calls == 0

    evidence = executor.action_evidence(
        outcome
    )

    assert evidence.capability_status is CapabilityStatus.VALID


def test_fetch_action_fetches_exact_url_without_search() -> None:
    tool = FakeInternetTool()
    executor = (
        ExternalVerificationExecutor(
            tool  # type: ignore[arg-type]
        )
    )

    outcome = executor.collect_fetch_action(
        source_id="internet",
        url=(
            "https://example.com/release"
        ),
        user_request="What is the current Python version?",
        freshness_required=True,
    )

    assert outcome.verified is True
    assert [
        call["resource"]
        for call in tool.calls
    ] == ["web_fetch"]


def test_failed_fetch_is_not_valid_evidence() -> None:
    tool = FakeInternetTool()
    tool.fetch_payloads = {}

    executor = (
        ExternalVerificationExecutor(
            tool  # type: ignore[arg-type]
        )
    )

    outcome = executor.collect_fetch_action(
        source_id="internet",
        url="https://example.com/release",
        user_request="current version",
        freshness_required=True,
    )

    assert outcome.verified is False
