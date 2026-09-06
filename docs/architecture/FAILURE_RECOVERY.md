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

For errors that explicitly set `model_recovery_required`, Orion tracks normalized
failure states request-locally within the unresolved recovery barrier. A fingerprint
contains the operation name, a canonical-argument identity, and error code; call IDs
and JSON key order do not change it. Parallel calls form one sorted state, so their
execution order does not change recovery meaning.

```text
(tool_name, canonical_argument_identity, error_code)
```

Changing arguments, tools, or error codes is not by itself progress. The tracker detects
both a repeated state and the shortest repeated multi-state cycle, such as
`A -> B -> A -> B`, using the ADR 0012 configured occurrence limits. Its bounded
history retains only normalized state identities and safe stall metadata; it does not
route tools, rewrite arguments, retry automatically, or answer for the model.

A successful ordinary result with no simultaneous recoverable error resolves the
outstanding failure chain. Expansion/control success does not erase unresolved failure
history. In a mixed success/error batch, the recoverable error remains unresolved, so
an unrelated success cannot hide a recurring failure. A new non-repeating failure is
returned to the model without being declared a stall. This is not a fixed tool-call
limit: ordinary successful reads and ambiguous evidence are not recovery cycles.

## RAG failures

Preserve document ingestion state and error details.

If parsing succeeds but indexing fails, the document must not be marked fully ready.
Malformed, encrypted, oversized, unsafe-archive, or unsupported document content fails
closed and remains visible as a failed ingestion rather than crashing the runtime.

## Cancellation

Users should be able to cancel long model/tool operations. Cancellation is not the same as semantic failure.

## No artificial usage ceiling

The architecture does not use fixed tool-call/model-call quotas as normal termination logic.

A process-level watchdog/transport timeout may terminate genuinely hung work so the application remains recoverable.
