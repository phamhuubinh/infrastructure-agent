# Chat runtime

## Purpose

Chat is Orion's universal interaction runtime.

A chat request should require no mode selection and no tool selection.

## Input

A model turn may receive:

- stable Orion system instructions;
- the complete current user message;
- recent conversation history;
- a bounded older conversation summary;
- metadata/content for explicitly attached/current documents when appropriate;
- a compact catalog of every registered ordinary tool and generic expansion control;
- full schemas only for ordinary tools expanded during this request.

## Flow

```text
user message
   ↓
persist user item
   ↓
assemble context
   ↓
call model with catalog + expansion control + request-exposed tools
   ↓
┌──────────────────────┬──────────────────────┐
│ direct/final response│ tool call            │
└───────────┬──────────┴───────────┬──────────┘
            │                      ↓
            │                 execute tool
            │                      ↓
            │                 ToolResult
            │                      ↓
            │                    model
            │                      │
            └──────────────────────┘
                        ↓
                    final answer
                        ↓
                    persist/stream
```

The tool loop can continue for as many useful calls as the model needs. The architecture does not define an artificial per-message tool-call quota.

Operational transport/process timeouts may still prevent a hung integration from blocking the application forever.

## Attachments

A file explicitly attached to the current chat is deterministic context:

- Orion knows the exact attachment identity;
- the model does not need to "discover" that the attachment exists;
- full content may be injected when small enough;
- larger content should be available through document/RAG tools in session scope.

## No pre-router

Do not implement:

```text
if prompt contains "document" → RAG
if prompt contains "Grafana"  → Grafana
if prompt contains "CPU"      → Linux
```

The model sees the request, catalog, and expansion control, then chooses its own
tools. Orion does not decide which catalog name to expand.
