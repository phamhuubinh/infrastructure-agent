# Failure and recovery

## Philosophy

Failures should be explicit and local to the failing component where possible.

## Model failures

Examples:

- endpoint unavailable;
- invalid provider response;
- transport timeout;
- context overflow.

Return a clear request failure or retry only when the error is plausibly transient and retry is safe.

## Tool failures

A tool failure returns a structured error to the model:

```text
tool unavailable
invalid input
connection failure
upstream error
timeout
not found
```

The model may:

- use another source;
- retry with corrected input when appropriate;
- explain the unavailable information;
- ask the user.

Do not convert a failed tool call into fake successful data.

## RAG failures

Preserve document ingestion state and error details.

If parsing succeeds but indexing fails, the document must not be marked fully ready.

## Cancellation

Users should be able to cancel long model/tool operations. Cancellation is not the same as semantic failure.

## No artificial usage ceiling

The architecture does not use fixed tool-call/model-call quotas as normal termination logic.

A process-level watchdog/transport timeout may terminate genuinely hung work so the application remains recoverable.
