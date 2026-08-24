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
- model-visible definitions for every registered tool.

## Flow

```text
user message
   ↓
persist user item
   ↓
assemble context
   ↓
call model with all registered tools
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

The model sees the request and chooses its own tools.
