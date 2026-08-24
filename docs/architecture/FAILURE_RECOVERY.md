# Failure and recovery

## Failure classes

Recommended terminal/runtime reasons:

- `model_failure`;
- `model_call_limit`;
- `tool_search_limit`;
- `tool_call_limit`;
- `no_progress`;
- `contract_failure`;
- `tool_not_exposed`;
- `authority_denied`;
- `permission_denied`;
- `approval_required` / `approval_denied`;
- `executor_failure`;
- `evidence_failure`;
- `persistence_failure`.

## Retry philosophy

Retry only when the failure is plausibly transient and retry is safe. Do not use retries to repair malformed authority or to hide a model loop.

## Duplicate successful calls

For exact repeated successful calls, return existing evidence when capability semantics permit it. For writes, capability-specific idempotency policy determines whether reuse, explicit re-approval, verification, or rejection is appropriate.

## No progress

Track fingerprints of repeated model outputs/tool calls and whether each iteration adds new exposure, approval state, evidence, or user input. Stop boundedly when nothing changes.

## Persistence recovery

Multi-store project/session mutations require transactional behavior or durable recovery journals/tombstones. Corrupt data should be quarantined/preserved, not silently treated as empty healthy state.

## Fail closed

Unknown capability, target/source, schema mismatch, unavailable isolation, malformed config, or ambiguous authority must block execution rather than guess a fallback.
