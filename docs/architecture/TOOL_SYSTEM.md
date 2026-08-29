# Tool system

## Goal

Tools give the model capabilities beyond its static parameters while keeping orchestration simple.

## One registry

There should be one authoritative registry containing every tool available to the runtime.

Conceptually:

```python
ToolDefinition(
    name="internet.search",
    description="Search the Internet",
    input_schema={...},
    handler_key="internet.search",
)
```

Canonical identities are defined in `CONTRACTS.md`.

The exact implementation may differ, but tool identity, schema, description, and handler binding must not be duplicated across semantic selectors/routers.

## Startup

```text
application startup
       ↓
discover/register configured tools
       ↓
validate ToolDefinition contracts
       ↓
build registry-derived exact-name catalog and expansion control
       ↓
all registered ordinary tools discoverable on every Chat/Project model turn
       ↓
model-controlled request-local schema exposure
```

## Runtime

```text
ModelToolCall
   ↓
normalize provider output
   ↓
tool exists?
   ↓
input schema valid?
   ↓
Orion attaches RuntimeScope
   ↓
ToolRunner
   ↓
tool implementation/integration
   ↓
canonical ToolResult
   ↓
Model
```

Orion validates structure, attaches deterministic application scope, and dispatches.

It does not second-guess the semantic reason the model chose the tool.

## Runtime scope

A tool call may need deterministic context that must not be model-selected, for example:

```text
session_id
active project_id
current attachment identities
```

Orion provides this as `RuntimeScope` to the tool implementation.

Example:

```text
model:
  knowledge.search(query="backup retention")

Orion runtime:
  session_id = S1
  project_id = Project A

Knowledge tool searches only sources valid for S1 / Project A.
```

The model chooses the query. Orion binds the application's actual scope.

## Current families

The current repository contains:

- Knowledge/RAG;
- calculator;
- Internet;
- Linux;
- Grafana;
- Zabbix.

These should join the same model-facing registry rather than separate semantic pipelines.

## Configuration

Global application settings may determine whether an integration can initialize and therefore register.

This is different from a conversation tool picker.

A tool that cannot initialize because required integration configuration is missing is absent from
the registry rather than represented as a manually disabled per-chat choice. Application health
remains a cheap process check and does not probe tools.

## Tool output

Tool results should use the canonical `ToolResult` shape and be:

- structured where practical;
- explicit about success/error;
- source-aware where applicable;
- safe for model context;
- free of raw credentials/secrets.

Large payloads should use selective reads, references, reduction, or retrieval rather than blindly flooding the model context.

Canonical tool results remain complete in persistence and public timeline APIs. The
Chat runtime may create a generic bounded model-visible projection for a model turn.
That projection preserves valid tool-call/result pairing, exact citation source
identities, errors, collection counts, and operation outcome metadata, and explicitly
describes any omitted structure. Duplicate provider tool-call IDs are rejected before
they can create ambiguous call/result pairing.

## Non-goals

The current target does not introduce:

- manual tool selection;
- semantic pre-routing;
- `capability.search`;
- user-selected or integration-routed tool exposure;
- product-level per-request tool-call quotas.
