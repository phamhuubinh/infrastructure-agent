# Engineering rules

## Architecture

- Build target contracts first.
- Prefer deleting obsolete code to adding compatibility glue.
- One concept has one owner and one source of truth.
- Do not maintain old and new agent protocols in parallel beyond explicit migration gates.

## Model boundary

- Model output is untrusted.
- Use native tool calls when available; strict provider-neutral fallback otherwise.
- Never repair malformed output into an executable action.
- Do not ask the model to mirror harness state it does not need to know.

## Capability boundary

- All executable operations are registered capabilities.
- Closed schemas only.
- Exact identities only.
- No default localhost/source.
- Non-applicable refs are omitted, not nullable authority fields.

## Execution

- Authorization precedes dispatch.
- Credentials resolved only after authorization.
- Result schemas are bounded and validated.
- Side-effecting actions require explicit idempotency/duplicate policy.
- Failure to establish required sandbox/isolation is a failure, not a fallback.

## Evidence

- Evidence is created only from validated execution/retrieval results.
- Dispatch is not success.
- Model final output references evidence; it does not construct evidence identity/provenance.

## Security

- Reject secret-shaped model/tool fields at boundaries.
- Bound text, arrays, nesting, output bytes and runtime.
- Treat internet/RAG/integration content as untrusted data.

## Quality

- Typed contracts over dictionary conventions.
- Pure validators where practical.
- Explicit enums for status/effect/reason.
- Deterministic fingerprints for actions/approvals/idempotency.
- No broad exception swallowing that turns errors into healthy results.

## Git and validation

Run the smallest relevant checks during implementation. Do not claim live/Docker/QA success unless actually run. Do not commit/push unless explicitly requested.
