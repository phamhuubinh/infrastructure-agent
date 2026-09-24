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
When such an instruction requires citations and the final model context has citation-eligible
sources, the model cites request-local aliases such as `[[source:S1]]`; it never needs to copy a
canonical `source_ref_id`. Citation eligibility is derived from evidence that actually survived
model projection. For row-addressable Internet search and Knowledge retrieval results, a source
whose row/segment was compacted away is not model-citable merely because its canonical `SourceRef`
remains persisted. Before
validation/persistence Orion resolves each visible alias back to its canonical source identity and
rewrites the presentation marker.

An answer without a required alias citation (including an answer with only Markdown links) enters
the existing single citation-correction attempt. Once that rejection occurs, the citation
obligation is sticky for the rest of the request: rebuilding a smaller correction context cannot
erase the obligation by making the visible-source set empty. A second omission therefore fails
closed as `missing_citation`. The obligation does not carry over to subsequent user requests.

Citation correction asks the model to re-answer the original user request from the currently
visible evidence while preserving all original requirements, including exact wording, scope,
and format. The rejected assistant draft is not replayed into the correction request because it
is not evidence and must not consume the evidence budget. The correction instruction is fixed-size
and tells the model to copy exact `evidence_ref` values already present in visible ToolResult
messages; it does not duplicate them into a dynamic allowlist. The original user request remains
visible, and safe tools remain available when evidence is missing.

The model never receives canonical source identity through the correction path. Strict
provider-bound context sizing uses the same request-local alias/pruning projection that is later
sent to the model, so canonical UUID length cannot by itself displace evidence that would fit in
the actual request. Unknown aliases, `source_id`, target/document IDs, URLs, and raw canonical IDs
do not resolve to a citation. If correction-time compaction leaves no citation-eligible evidence,
the model may obtain fresh evidence with a safe tool, but an uncited terminal answer cannot become
valid merely because the runtime's own correction projection dropped the prior source.

Every citation rejection, including one followed by successful correction, emits an opt-in
`citation_validation` diagnostic with the request/model-turn identity, error kind, canonical
`attempted_source_ref_ids`, request-local `attempted_evidence_refs` when an unresolved model
alias was supplied, `visible_source_ref_ids`, and whether correction had already been attempted. Terminal citation failure notices also include these ID lists. Rejected assistant
content is not added to these records.

If an assistant draft abandons required tool recovery, the forced recovery model request appends
an ephemeral user continuation after the draft, asking the model to continue the original request
with schema-valid arguments. The draft remains in the timeline, but this continuation is never
persisted as a real user message and does not alter the request scope. It is included in context
budget accounting; registered tools remain exposed on the forced recovery turn. Subsequent tool
result turns do not inherit the synthetic user continuation.
