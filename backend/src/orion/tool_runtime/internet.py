"""Internet tool definitions and canonical result normalisation."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from orion.contracts import SourceRef, ToolCall, ToolDefinition, ToolError, ToolResult
from orion.integrations import InternetClient, InternetClientError
from orion.tool_runtime.registry import ToolRegistration


def internet_registrations(client: InternetClient) -> tuple[ToolRegistration, ...]:
    return (
        ToolRegistration(definition=internet_search_definition(), handler=_search(client)),
        ToolRegistration(definition=internet_fetch_definition(), handler=_fetch(client)),
    )


def internet_search_definition() -> ToolDefinition:
    return ToolDefinition(
        name="internet.search",
        description="Search current Internet information and return bounded, source-aware results.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 500},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler_key="internet.search",
    )


def internet_fetch_definition() -> ToolDefinition:
    return ToolDefinition(
        name="internet.fetch",
        description=(
            "Fetch one public HTTP(S) URL and return bounded textual content with provenance."
        ),
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string", "minLength": 1, "maxLength": 2048}},
            "required": ["url"],
            "additionalProperties": False,
        },
        handler_key="internet.fetch",
    )


def _search(client: InternetClient) -> Callable[[ToolCall], ToolResult]:
    def handler(call: ToolCall) -> ToolResult:
        try:
            results = client.search(
                str(call.arguments["query"]), int(call.arguments.get("limit", 5))
            )
        except InternetClientError as error:
            return _failure(call, error)
        sources = tuple(
            _source(result.url, result.title, result.retrieved_at) for result in results
        )
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={
                "results": [
                    {
                        "source_ref_id": source.source_ref_id,
                        "url": result.url,
                        "title": result.title,
                        "snippet": result.snippet,
                        "retrieved_at": result.retrieved_at.isoformat(),
                    }
                    for result, source in zip(results, sources, strict=True)
                ]
            },
            sources=sources,
        )

    return handler


def _fetch(client: InternetClient) -> Callable[[ToolCall], ToolResult]:
    def handler(call: ToolCall) -> ToolResult:
        try:
            fetched = client.fetch(str(call.arguments["url"]))
        except InternetClientError as error:
            return _failure(call, error)
        source = _source(fetched.url, fetched.title, fetched.retrieved_at)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={
                "source_ref_id": source.source_ref_id,
                "url": fetched.url,
                "title": fetched.title,
                "text": fetched.text,
                "retrieved_at": fetched.retrieved_at.isoformat(),
            },
            sources=(source,),
        )

    return handler


def _failure(call: ToolCall, error: InternetClientError) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status="error",
        error=ToolError(code=error.code, message=error.message, retryable=error.retryable),
    )


def _source(url: str, title: str | None, retrieved_at) -> SourceRef:  # type: ignore[no-untyped-def]
    return SourceRef(
        source_ref_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"orion:internet:{url}")),
        source_kind="internet",
        source_id=url,
        label=title or url,
        url=url,
        retrieved_at=retrieved_at,
    )
