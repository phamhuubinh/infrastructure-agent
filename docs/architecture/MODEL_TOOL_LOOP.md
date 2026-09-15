# Model-tool loop

Chat and Project use the same model-driven loop and the same canonical `ToolRegistry`.
There is no manual picker or semantic pre-router.

```text
direct request: user -> deterministic context + all registered schemas -> model -> answer
tool request:   user -> deterministic context + all registered schemas -> model -> tools -> model -> answer
```

A direct request normally makes one model call. A request whose first turn calls tools normally
makes two: one decision call and one synthesis call after current-request `ToolResult` data.
Independent read-only calls emitted together are validated then run concurrently and do not add
model turns. Later turns are only for a genuine dependency, recoverable invalid call, or citation
correction. Mutations stay ordered and application-authorized.

Every call in an emitted turn is prepared through the canonical runner (schema validation,
scope binding, and authorization) before any handler starts. Read batches are drained on
interruption; mutations form ordering boundaries. Each completed or interrupted execution
persists its own correlated result and measured elapsed time immediately, rather than waiting
for later calls. A later deadline must not erase an already verified mutation outcome.
Results correlate by `call_id`; completion order need not equal dispatch order. Synthesis
starts only after the batch has returned all results. Per-tool elapsed time measures that
execution, not the wait for the slowest member of its batch.

All registered model-callable schemas are supplied on every normal turn. Schema visibility never
authorizes execution: `ToolRunner` validates arguments, binds `RuntimeScope`, and enforces the
mutation allowlist/default deny policy.

The provider-neutral input has one `system_instructions` value plus user/assistant/tool messages.
The OpenAI-compatible adapter emits at most one leading system message and never a system role
after conversation begins.

`ToolResult` data is evidence. Prior assistant prose is continuity only, not current evidence.
Current-state claims require ToolResults from the current request; old measurements, when
explicitly included for comparison, are historical. Citation validation validates syntax,
visibility, and provenance only; it does not establish semantic entailment.
