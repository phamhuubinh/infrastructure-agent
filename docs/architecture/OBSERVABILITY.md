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

Model turns should have a per-request model-turn correlation ID. Record monotonic elapsed
time for model and tool phase start/finish/failure/cancellation; elapsed time is
not evidence of provider queueing or hidden reasoning.

- session ID;
- request ID;
- model call ID;
- tool call ID;
- tool name;
- project/document ID where applicable.

## Logging

Log safe structured metadata.

Do not log raw secrets, bearer tokens, SSH private keys, database passwords, or unrestricted provider payloads.

Detailed model-input evidence is disabled by default. A test-only opt-in sink may retain
redacted, explicitly capped tool-result projections, exposed tool names, visible source IDs,
byte counts, and projection omissions. It must not retain provider headers/native payloads,
hidden reasoning, or unrestricted user/system/developer prompts, and sink failures must not
affect request execution.

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
