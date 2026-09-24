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

Terminal citation validation checks the original current user request for direct English or
Vietnamese citation/attribution output instructions. This conservative check recognizes explicit
commands and citation modifiers, excludes quoted examples/code, and honors later explicit opt-outs;
it is not a general semantic intent classifier. Other wording remains governed by the model's
citation policy. It runs after the model and does not affect tool exposure or execution.
When such an instruction requires citations and the final model context has visible sources,
an answer without canonical `[[source:<source_ref_id>]]` markers (including an answer with only
Markdown links) enters the existing single citation-correction attempt. An ordinary answer or
an answer without visible sources does not acquire this requirement. A second omission fails
validation as `missing_citation`. The correction draft and user instruction remain ephemeral;
the requirement does not carry over to subsequent requests.

Citation correction asks the model to re-answer the original user request from the currently
visible evidence while preserving all original requirements, including exact wording, scope,
and format. It must reconsider the answer's content, not merely attach a marker to the draft.
The original user request remains visible, and safe tools remain available when evidence is missing.

The synthetic citation-correction user message includes an explicit JSON allowlist of exact
`source_ref_id` values from the correction request's visible sources. Its bytes are reserved
before dispatch; if reserving that space changes visible sources, the allowlist is rebuilt
from the resulting context. IDs are copied unchanged, with no automatic mapping from a rejected
ID to a valid one. An empty allowlist permits no citation. A second invalid answer still fails closed.

Every citation rejection, including one followed by successful correction, emits an opt-in
`citation_validation` diagnostic with the request/model-turn identity, error kind,
`attempted_source_ref_ids`, `visible_source_ref_ids`, and whether correction had already been
attempted. Terminal citation failure notices also include these ID lists. Rejected assistant
content is not added to these records.

If an assistant draft abandons required tool recovery, the forced recovery model request appends
an ephemeral user continuation after the draft, asking the model to continue the original request
with schema-valid arguments. The draft remains in the timeline, but this continuation is never
persisted as a real user message and does not alter the request scope. It is included in context
budget accounting; registered tools remain exposed on the forced recovery turn. Subsequent tool
result turns do not inherit the synthetic user continuation.
