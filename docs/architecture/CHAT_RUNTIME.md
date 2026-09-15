# Chat runtime

Chat is Orion's universal interaction runtime; Project uses this exact runtime with a
project-scoped knowledge source. Neither surface has a mode selector or tool picker.

Each request builds deterministic bounded context with one leading system instruction, the full
current user message, recent complete conversation turns, current attachment/project identity,
and all registered model-callable schemas. It does not run an LLM summary/checkpoint preparation
step. Legacy checkpoint data is retained only for persistence compatibility.

```text
direct: user -> model -> terminal answer
tool:   user -> model -> validate/execute ToolResults -> model -> terminal answer
```

Independent read-only calls returned together are validated and executed concurrently. Mutations
remain serialized and blocked by default unless the application-owned authorization policy grants
the exact `(tool_name, target_ref)` permission. The model decides semantically whether tools are
useful; Orion does not keyword-route requests.

Current-request `ToolResults` are factual evidence. Assistant history supplies conversational
continuity but cannot substitute for refreshed infrastructure evidence. A request normally has
one model call without tools and two with a first-turn tool call; extra calls need dependency,
recovery, or citation-correction justification.
