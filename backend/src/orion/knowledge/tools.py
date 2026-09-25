"""Knowledge operations registered in the common ToolRegistry."""

from __future__ import annotations

from collections.abc import Callable

from orion.contracts import ReadProgress, ToolCall, ToolDefinition, ToolResult
from orion.knowledge.service import KnowledgeService
from orion.tool_runtime.registry import ToolRegistration

_EXACT_DOCUMENT_ID_DESCRIPTION = (
    "Exact visible document_id from attachment metadata, knowledge.search, or "
    "knowledge.list_documents; never invent one or use a name/title. For content lookup "
    "without an ID, use knowledge.search."
)


def knowledge_registrations(service: KnowledgeService) -> tuple[ToolRegistration, ...]:
    return tuple(
        ToolRegistration(definition=definition, handler=handler)
        for definition, handler in (
            (list_documents_definition(), _list_documents(service)),
            (search_definition(), _search(service)),
            (read_definition(), _read(service)),
            (source_metadata_definition(), _source_metadata(service)),
        )
    )


def list_documents_definition() -> ToolDefinition:
    return ToolDefinition(
        name="knowledge.list_documents",
        description=(
            "List visible document metadata only; returns no content/citations. metadata browsing "
            "only: do not use as a prerequisite for content QA; use knowledge.search directly. "
            "Orion binds current scope."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler_key="knowledge.list_documents",
    )


def search_definition() -> ToolDefinition:
    return ToolDefinition(
        name="knowledge.search",
        description=(
            "Primary retrieval tool for fact/topic/quote/attribution questions in current scope. "
            "Search directly without calling knowledge.list_documents first. Returns citable "
            "ToolResult sources; use knowledge.read for sequential/full context."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Content query for evidence to retrieve.",
                    "minLength": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max ranked segments (1-20; default 5).",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
                "document_ids": {
                    "type": "array",
                    "description": (
                        "Optional exact visible IDs; omit unless exact document_id values "
                        "are visible now."
                    ),
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler_key="knowledge.search",
    )


def read_definition() -> ToolDefinition:
    return ToolDefinition(
        name="knowledge.read",
        description=(
            "Read a bounded sequential window from one exact document in current scope. Use for "
            "whole-document/section/adjacent/iterative reading; it is not the default "
            "content-discovery tool. Use knowledge.search for discovery. Successful reads return "
            "citable ToolResult sources; continue with next_cursor."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": _EXACT_DOCUMENT_ID_DESCRIPTION,
                    "minLength": 1,
                },
                "section": {"type": "string", "minLength": 1},
                "cursor": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {
                    "type": "integer",
                    "description": (
                        "Sequential segments this window (1-8; default 5); "
                        "continue with next_cursor."
                    ),
                    "minimum": 1,
                    "maximum": 8,
                    "default": 5,
                },
            },
            "required": ["document_id"],
            "additionalProperties": False,
        },
        handler_key="knowledge.read",
    )


def source_metadata_definition() -> ToolDefinition:
    return ToolDefinition(
        name="knowledge.source_metadata",
        description=(
            "Get structure and provenance metadata only for documents visible in the current "
            "knowledge scope, including session attachments and active Project documents. This "
            "does not read document contents and returns no citable ToolResult sources. It cannot "
            "support quoting or citing document contents; use knowledge.read or knowledge.search "
            "for that purpose."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": _EXACT_DOCUMENT_ID_DESCRIPTION,
                    "minLength": 1,
                }
            },
            "additionalProperties": False,
        },
        handler_key="knowledge.source_metadata",
    )


def _list_documents(service: KnowledgeService) -> Callable[[ToolCall], ToolResult]:
    def handler(call: ToolCall) -> ToolResult:
        documents = service.list_documents(call.runtime_scope)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"documents": [document.model_dump(mode="json") for document in documents]},
        )

    return handler


def _search(service: KnowledgeService) -> Callable[[ToolCall], ToolResult]:
    def handler(call: ToolCall) -> ToolResult:
        try:
            segments = service.search(
                call.runtime_scope,
                str(call.arguments["query"]),
                int(call.arguments.get("limit", 5)),
                tuple(str(document_id) for document_id in call.arguments.get("document_ids", [])),
            )
        except PermissionError:
            return ToolResult.failure(
                call.call_id,
                call.tool_name,
                "scope_violation",
                "One or more document_ids are outside the current knowledge scope. "
                "Retry with only exact visible document_ids; if the request does not "
                "require a specific document, omit document_ids to search the current scope.",
                model_recovery_required=True,
            )
        sources = tuple(service.source_for_segment(segment) for segment in segments)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"segments": [segment.model_dump(mode="json") for segment in segments]},
            sources=sources,
            read_progress=ReadProgress(
                observation_id=(
                    "knowledge.search:"
                    f"{call.runtime_scope.project_id or call.runtime_scope.session_id}"
                ),
                coverage={
                    "query": call.arguments["query"],
                    "document_ids": call.arguments.get("document_ids", []),
                },
                certainty="confirmed",
            ),
        )

    return handler


def _read(service: KnowledgeService) -> Callable[[ToolCall], ToolResult]:
    def handler(call: ToolCall) -> ToolResult:
        try:
            window = service.read(
                call.runtime_scope,
                str(call.arguments["document_id"]),
                str(call.arguments["section"]) if "section" in call.arguments else None,
                int(call.arguments.get("cursor", 0)),
                int(call.arguments.get("limit", 5)),
            )
        except PermissionError as error:
            return ToolResult.failure(call.call_id, call.tool_name, "scope_violation", str(error))
        except LookupError as error:
            if str(error) == "Document was not found":
                return ToolResult.failure(
                    call.call_id,
                    call.tool_name,
                    "not_found",
                    "Document was not found. Obtain an exact visible document_id with "
                    "knowledge.list_documents or knowledge.search, then retry; do not use "
                    "a name or title as document_id.",
                    model_recovery_required=True,
                )
            return ToolResult.failure(call.call_id, call.tool_name, "not_found", str(error))
        sources = tuple(service.source_for_segment(segment) for segment in window.segments)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={
                "document": window.document.model_dump(mode="json"),
                "segments": [segment.model_dump(mode="json") for segment in window.segments],
                "cursor": window.cursor,
                "next_cursor": window.next_cursor,
                "complete": window.complete,
                "total_segments": window.total_segments,
                "section": call.arguments.get("section"),
            },
            sources=sources,
            read_progress=ReadProgress(
                observation_id=f"knowledge.read:{window.document.document_id}",
                cursor=window.cursor,
                coverage={
                    "section": call.arguments.get("section"),
                    "limit": call.arguments.get("limit", 5),
                },
                certainty="confirmed",
            ),
        )

    return handler


def _source_metadata(service: KnowledgeService) -> Callable[[ToolCall], ToolResult]:
    def handler(call: ToolCall) -> ToolResult:
        try:
            metadata = service.source_metadata(
                call.runtime_scope,
                str(call.arguments["document_id"]) if "document_id" in call.arguments else None,
            )
        except PermissionError as error:
            return ToolResult.failure(call.call_id, call.tool_name, "scope_violation", str(error))
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"document_metadata": metadata},
        )

    return handler
