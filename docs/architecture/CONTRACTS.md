# Canonical runtime contracts

## Purpose

This document defines the canonical data contracts shared by Chat, Project, model adapters, tools, and document/RAG services.

These contracts are architectural identities. Provider adapters, API DTOs, persistence rows, and integration-specific objects may have different physical representations, but they must map into these concepts without changing their semantics.

The goal is to prevent the same concept from being represented differently in multiple routers, providers, or tool families.

## Design rules

1. Chat and Project use the same runtime contracts.
2. Provider-native response objects do not cross the model adapter boundary.
3. Tool-specific implementation objects do not become runtime contracts.
4. Project scope is supplied by Orion runtime state, not invented by the model.
5. Retrieved text and tool output are data, never system instructions.
6. IDs used for scoping are opaque application identities, not fuzzy names.
7. The model chooses semantic actions; Orion binds deterministic application context.

## ModelTurn

A normalized model turn represents what the model wants to do next.

```text
ModelTurn
├── AssistantMessage
└── ToolCalls
```

Conceptually:

```python
@dataclass
class AssistantMessage:
    content: str

@dataclass
class ModelToolCall:
    call_id: str
    tool_name: str
    arguments: dict

@dataclass
class ToolCalls:
    calls: list[ModelToolCall]
```

Provider adapters may receive native tool-call IDs. Orion may preserve them for correlation, but provider-specific response types must not leak into the runtime.

## ToolDefinition

A `ToolDefinition` is the single model-facing definition of one callable tool operation.

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict
    handler_key: str
```

Required properties:

- `name` is globally unique in the runtime;
- `description` explains when the tool is useful;
- `input_schema` is explicit and machine-validatable;
- `handler_key` resolves to one registered implementation;
- credentials are not model arguments unless they are genuinely part of the user's requested data.

Do not duplicate tool identity/schema in a separate semantic selector.

## ToolCall

A runtime `ToolCall` is a validated request to invoke a registered tool.

```python
@dataclass
class ToolCall:
    call_id: str
    tool_name: str
    arguments: dict
    runtime_scope: "RuntimeScope"
```

`runtime_scope` is attached by Orion. It is not freely authored by the model.

## RuntimeScope

`RuntimeScope` carries deterministic application context relevant to a tool call.

```python
@dataclass
class RuntimeScope:
    session_id: str
    project_id: str | None
    attachment_ids: tuple[str, ...]
```

Future fields may include workspace or user identities, but they remain application-owned context.

### Important

If a conversation is inside Project A, the model does not gain authority to retrieve Project B by sending `project_id="B"` in ordinary knowledge-tool arguments.

Project-aware tools receive the active `RuntimeScope` from Orion and enforce it internally.

## ToolResult

Every successful or failed tool invocation returns one canonical runtime result.

```python
@dataclass
class ToolResult:
    call_id: str
    tool_name: str
    status: Literal["success", "error"]
    data: object | None
    error: "ToolError | None"
    sources: list["SourceRef"]
```

Tool results should be structured where practical and safe to send back to the model.

## ToolError

```python
@dataclass
class ToolError:
    code: str
    message: str
    retryable: bool = False
```

Typical codes include:

```text
invalid_input
not_found
unavailable
connection_error
timeout
upstream_error
scope_violation
```

Do not turn failures into fake successful tool data.

## KnowledgeSourceRef

A knowledge source identifies a retrieval scope, not a free-form query hint.

```python
@dataclass
class KnowledgeSourceRef:
    kind: Literal["session", "project", "shared"]
    source_id: str
```

Examples:

```text
session:<session_id>
project:<project_id>
shared:<library_id>
```

The active project source is derived by Orion from `RuntimeScope.project_id`.

## DocumentRef

```python
@dataclass
class DocumentRef:
    document_id: str
    source: KnowledgeSourceRef
    name: str
    media_type: str | None
```

Document identity must be preserved through ingestion, retrieval, exact reads, and citations.

## RetrievedSegment

```python
@dataclass
class RetrievedSegment:
    document: DocumentRef
    segment_id: str
    text: str
    page: int | None
    section: str | None
    score: float | None
```

Retrieval implementations may add ranking/debug metadata internally, but model-facing output should remain concise and source-aware.

## SourceRef and Citation

A tool result may include source references that the assistant can cite.

```python
@dataclass
class SourceRef:
    source_kind: str
    source_id: str
    document_id: str | None
    segment_id: str | None
    page: int | None
    section: str | None
    label: str | None
```

A final citation is a presentation-level reference to one or more `SourceRef` values. Citation rendering belongs to the UI/API presentation layer, not to retrieval ranking logic.

## TimelineItem

Persist public conversation/runtime state as typed timeline items.

```text
UserMessage
AssistantMessage
ToolCallItem
ToolResultItem
AttachmentItem
RuntimeNotice
```

Do not persist private hidden model reasoning.

Each item should carry at least:

```text
item_id
session_id
created_at
kind
public payload
```

Tool items additionally carry `call_id` and `tool_name`.

## Project binding rule

The canonical flow for a Project knowledge call is:

```text
Project chat request
    ↓
Orion loads active project_id from session/project state
    ↓
RuntimeScope(project_id=...)
    ↓
Model calls knowledge.search(query=...)
    ↓
ToolRunner passes RuntimeScope to Knowledge tool
    ↓
Knowledge service searches only:
    - current session source where applicable
    - active project source
    - explicitly configured shared source if allowed by product behavior
```

The model chooses **that retrieval is useful** and **what to search for**.

Orion chooses **which deterministic project scope the request belongs to**.

## Non-goals

These contracts do not introduce:

- semantic pre-routing;
- manual tool selection;
- dynamic capability discovery;
- per-request tool allowlists;
- model-visible workflow states;
- product-level tool-call quotas.

If future product requirements add such behavior, update the architecture explicitly rather than overloading these contracts.
