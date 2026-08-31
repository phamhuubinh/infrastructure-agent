"""Knowledge operations registered in the common ToolRegistry."""

from __future__ import annotations

from collections.abc import Callable

from orion.contracts import ToolCall, ToolDefinition, ToolResult
from orion.knowledge.service import KnowledgeService
from orion.tool_runtime.registry import ToolRegistration

_EXACT_DOCUMENT_ID_DESCRIPTION = (
    "Exact visible document_id already returned by knowledge.list_documents or "
    "knowledge.search earlier in this session; never invent, guess, or infer one from the "
    "request text, a document name, or a title. If no document_id is yet visible, call "
    "knowledge.list_documents or knowledge.search first."
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
            "List metadata for ready documents visible in the current knowledge scope, including "
            "session attachments and active Project documents. This does not read document "
            "contents and returns no citation sources. To answer from or cite document contents, "
            "expand and call knowledge.read or knowledge.search using an exact returned "
            "document_id. This tool takes no parameters; Orion binds session and Project scope "
            "from the current runtime context and model arguments cannot override it."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler_key="knowledge.list_documents",
    )


def search_definition() -> ToolDefinition:
    return ToolDefinition(
        name="knowledge.search",
        description=(
            "Search documents visible in the current knowledge scope, including session "
            "attachments and active Project documents. "
            "Successful matches return citable ToolResult sources. Use exact read for full "
            "documents."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "document_ids": {
                    "type": "array",
                    "description": (
                        "Optional exact visible document_ids from knowledge.list_documents or "
                        "knowledge.search; do not use document names or titles."
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
            "Read a bounded window from one exact document visible in the current knowledge "
            "scope, including session attachments and active Project documents, or named section. "
            "Successful reads return citable ToolResult sources. Continue with next_cursor until "
            "complete for whole-document work."
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
                "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
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
        except PermissionError as error:
            return ToolResult.failure(call.call_id, call.tool_name, "scope_violation", str(error))
        sources = tuple(service.source_for_segment(segment) for segment in segments)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"segments": [segment.model_dump(mode="json") for segment in segments]},
            sources=sources,
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
