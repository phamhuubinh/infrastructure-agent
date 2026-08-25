"""Provider-neutral canonical contracts for the Orion runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CanonicalModel(BaseModel):
    """Strict base class so malformed provider/tool data is rejected early."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AssistantMessage(CanonicalModel):
    content: str = ""
    # These are presentation references, not document IDs supplied by the model.
    # Orion validates them against SourceRef values actually returned by tools.
    citation_source_ref_ids: tuple[str, ...] = ()


class ModelToolCall(CanonicalModel):
    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]


class ModelTurn(CanonicalModel):
    """A normalized provider response; content and tool calls may coexist."""

    assistant: AssistantMessage | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()

    @model_validator(mode="after")
    def require_assistant_or_tool_call(self) -> ModelTurn:
        if self.assistant is None and not self.tool_calls:
            raise ValueError("ModelTurn requires assistant content or at least one tool call")
        return self


class RuntimeScope(CanonicalModel):
    session_id: str = Field(min_length=1)
    project_id: str | None = None
    attachment_ids: tuple[str, ...] = ()
    principal_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)


class ToolDefinition(CanonicalModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    description: str = Field(min_length=1)
    input_schema: dict[str, Any]
    handler_key: str = Field(min_length=1)

    @field_validator("input_schema")
    @classmethod
    def require_object_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "object":
            raise ValueError("tool input_schema must have type 'object'")
        return value

    def provider_schema(self) -> dict[str, Any]:
        """The only tool shape that crosses into a model provider."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolCall(CanonicalModel):
    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    runtime_scope: RuntimeScope


class ToolError(CanonicalModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False


class KnowledgeSourceRef(CanonicalModel):
    kind: Literal["session", "project", "shared"]
    source_id: str = Field(min_length=1)


class DocumentRef(CanonicalModel):
    document_id: str = Field(min_length=1)
    source: KnowledgeSourceRef
    name: str = Field(min_length=1)
    media_type: str | None = None


class RetrievedSegment(CanonicalModel):
    document: DocumentRef
    segment_id: str = Field(min_length=1)
    text: str
    page: int | None = None
    section: str | None = None
    score: float | None = None


class SourceRef(CanonicalModel):
    source_ref_id: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    document_id: str | None = None
    segment_id: str | None = None
    page: int | None = None
    section: str | None = None
    label: str | None = None


class Citation(CanonicalModel):
    source_ref_ids: tuple[str, ...] = Field(min_length=1)


def citations_are_visible(
    citation_source_ref_ids: tuple[str, ...], visible_source_ref_ids: set[str]
) -> bool:
    """Return whether every presentation citation names a tool-visible source."""
    return all(source_ref_id in visible_source_ref_ids for source_ref_id in citation_source_ref_ids)


class ToolResult(CanonicalModel):
    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    status: Literal["success", "error"]
    data: Any | None = None
    error: ToolError | None = None
    sources: tuple[SourceRef, ...] = ()

    @field_validator("error")
    @classmethod
    def error_matches_status(cls, value: ToolError | None, info: Any) -> ToolError | None:
        status = info.data.get("status")
        if status == "error" and value is None:
            raise ValueError("error ToolResult requires a ToolError")
        if status == "success" and value is not None:
            raise ValueError("successful ToolResult cannot contain ToolError")
        return value

    @classmethod
    def failure(cls, call_id: str, tool_name: str, code: str, message: str) -> ToolResult:
        return cls(
            call_id=call_id,
            tool_name=tool_name,
            status="error",
            error=ToolError(code=code, message=message),
        )


class ContextMessage(CanonicalModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ModelToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None
    citation_source_ref_ids: tuple[str, ...] = ()


class AssistantDelta(CanonicalModel):
    """A provider-normalized public fragment of assistant content."""

    content: str = Field(min_length=1)


class ToolCallDelta(CanonicalModel):
    """A provider-normalized fragment of a tool call under construction."""

    index: int = Field(ge=0)
    call_id: str | None = None
    tool_name: str | None = None
    arguments_delta: str = ""


class ModelTurnCompleted(CanonicalModel):
    """The one reconstructed canonical model turn emitted at stream completion."""

    turn: ModelTurn


TimelineKind = Literal[
    "user_message",
    "assistant_message",
    "tool_call",
    "tool_result",
    "attachment",
    "runtime_notice",
]


class TimelineItem(CanonicalModel):
    item_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    created_at: datetime
    kind: TimelineKind
    payload: dict[str, Any]
    call_id: str | None = None
    tool_name: str | None = None
