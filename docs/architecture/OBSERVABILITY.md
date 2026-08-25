# Observability

## Goal

Automatic tool use must be debuggable.

A developer/operator should be able to reconstruct:

```text
user message
→ model call
→ tool call
→ tool result
→ next model call
→ final answer
```

without exposing private hidden reasoning.

## Recommended events

```text
request.accepted
model.started
model.completed
tool.started
tool.completed
tool.failed
rag.ingestion.started
rag.ingestion.completed
rag.ingestion.failed
document.uploaded
final.started
request.completed
request.failed
```

Include correlation IDs such as:

- session ID;
- request ID;
- model call ID;
- tool call ID;
- tool name;
- project/document ID where applicable.

## Logging

Log safe structured metadata.

Do not log raw secrets, bearer tokens, SSH private keys, database passwords, or unrestricted provider payloads.

## Metrics

Useful local diagnostics:

- model latency;
- tool latency/failures;
- RAG ingestion/query latency;
- retrieval result counts;
- model/tool loop count as diagnostic data;
- context size;
- streaming failures;
- integration health.

These metrics observe behavior; they are not a quota system.
