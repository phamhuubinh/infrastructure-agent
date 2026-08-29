"""Provider-neutral canonical contracts for the Orion runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal, NoReturn

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenJSONDict(dict[str, Any]):
    """JSON-serializable dictionary whose nested snapshot cannot be mutated."""

    @staticmethod
    def _immutable() -> NoReturn:
        raise TypeError("frozen JSON snapshot cannot be mutated")

    def __setitem__(self, key: str, value: Any) -> None:
        self._immutable()

    def __delitem__(self, key: str) -> None:
        self._immutable()

    def clear(self) -> None:
        self._immutable()

    def pop(self, key: str, default: Any = None) -> Any:
        self._immutable()

    def popitem(self) -> tuple[str, Any]:
        self._immutable()

    def setdefault(self, key: str, default: Any = None) -> Any:
        self._immutable()

    def update(self, *args: Any, **kwargs: Any) -> None:
        self._immutable()

    def __ior__(self, other: object) -> FrozenJSONDict:  # type: ignore[override,misc]
        self._immutable()

    def __deepcopy__(self, memo: dict[int, object]) -> FrozenJSONDict:
        return self


class FrozenJSONList(list[Any]):
    """JSON-serializable list whose snapshot cannot be mutated."""

    @staticmethod
    def _immutable() -> NoReturn:
        raise TypeError("frozen JSON snapshot cannot be mutated")

    def __setitem__(self, key: int | slice, value: Any) -> None:  # type: ignore[override]
        self._immutable()

    def __delitem__(self, key: int | slice) -> None:  # type: ignore[override]
        self._immutable()

    def append(self, value: Any) -> None:
        self._immutable()

    def clear(self) -> None:
        self._immutable()

    def extend(self, values: Any) -> None:
        self._immutable()

    def insert(self, index: int, value: Any) -> None:  # type: ignore[override]
        self._immutable()

    def pop(self, index: int = -1) -> Any:  # type: ignore[override]
        self._immutable()

    def remove(self, value: Any) -> None:
        self._immutable()

    def reverse(self) -> None:
        self._immutable()

    def sort(self, *args: Any, **kwargs: Any) -> None:
        self._immutable()

    def __iadd__(self, values: Any) -> FrozenJSONList:  # type: ignore[misc]
        self._immutable()

    def __imul__(self, value: int) -> FrozenJSONList:  # type: ignore[override,misc]
        self._immutable()

    def __deepcopy__(self, memo: dict[int, object]) -> FrozenJSONList:
        return self


def freeze_json(value: Any) -> Any:
    """Recursively freeze JSON-compatible data while retaining JSON serialization."""
    if isinstance(value, dict):
        return FrozenJSONDict({key: freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return FrozenJSONList(freeze_json(item) for item in value)
    return value


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


class ModelUsage(CanonicalModel):
    """Provider-reported token usage for one normalized model turn."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


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
    # Registry metadata only.  It deliberately does not cross the provider boundary.
    operation_kind: Literal["read", "mutation"] = "read"

    @field_validator("input_schema")
    @classmethod
    def require_object_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "object":
            raise ValueError("tool input_schema must have type 'object'")
        return value

    def provider_schema(self) -> dict[str, Any]:
        """Return the compact, deterministic provider projection of this tool.

        ``input_schema`` remains the complete canonical JSON Schema used by the
        ToolRegistry to validate every model call.  Providers receive only the
        structural cues needed to choose a tool and form valid arguments;
        numeric bounds are included, while regexes, defaults, and closed-object
        enforcement stay server-side.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _provider_schema_projection(self.input_schema),
            },
        }


def _provider_schema_projection(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Keep generic argument-forming cues without duplicating all validation rules."""
    projection: dict[str, Any] = {}
    for key in ("type", "description", "format", "enum", "const", "minimum", "maximum"):
        if key in schema:
            projection[key] = _json_snapshot(schema[key])
    if "properties" in schema:
        properties = schema["properties"]
        if isinstance(properties, Mapping):
            projection["properties"] = {
                str(name): _provider_schema_projection(value)
                for name, value in properties.items()
                if isinstance(value, Mapping)
            }
    if "items" in schema and isinstance(schema["items"], Mapping):
        projection["items"] = _provider_schema_projection(schema["items"])
    if "oneOf" in schema and isinstance(schema["oneOf"], (list, tuple)):
        projection["oneOf"] = [
            _provider_schema_projection(option)
            for option in schema["oneOf"]
            if isinstance(option, Mapping)
        ]
    if "required" in schema:
        projection["required"] = _json_snapshot(schema["required"])
    return projection


def _json_snapshot(value: Any) -> Any:
    """Copy JSON-compatible values so provider projections cannot alias inputs."""
    if isinstance(value, Mapping):
        return {str(key): _json_snapshot(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_snapshot(item) for item in value]
    return value


class ToolExpansionRequest(CanonicalModel):
    """Model-requested expansion of exact ordinary tool names."""

    tool_names: tuple[str, ...] = Field(min_length=1)


class ToolCall(CanonicalModel):
    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    runtime_scope: RuntimeScope
    # This is Orion-owned execution context, never model input or persisted result data.
    cancellation_requested: Callable[[], bool] | None = Field(default=None, exclude=True)


class ToolError(CanonicalModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    # Distinct from transport/execution retryability: this means the model can
    # safely choose a different in-scope recovery action for the user request.
    model_recovery_required: bool = False
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
    # Non-document sources (for example Internet retrieval) retain their canonical
    # citation identity while adding only the presentation provenance they need.
    url: str | None = None
    retrieved_at: datetime | None = None


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
    def failure(
        cls,
        call_id: str,
        tool_name: str,
        code: str,
        message: str,
        *,
        model_recovery_required: bool = False,
    ) -> ToolResult:
        return cls(
            call_id=call_id,
            tool_name=tool_name,
            status="error",
            error=ToolError(
                code=code,
                message=message,
                model_recovery_required=model_recovery_required,
            ),
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
    usage: ModelUsage | None = None


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
