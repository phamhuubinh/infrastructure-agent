# Events and observability

## Canonical event stream

Every public lifecycle transition is emitted once into a single typed event stream. Logs, UI progress, metrics, and audit views are projections of this stream rather than parallel truths.

Recommended events:

```text
request.started
model.started
model.completed
capability.search.started
capability.search.completed
tool.proposed
tool.rejected
authority.validated
approval.requested
approval.resolved
tool.started
tool.completed
tool.failed
evidence.created
final.created
request.completed
request.failed
```

## Correlation IDs

Include where applicable:

- session_id;
- request_id;
- model_call_id;
- tool_call_id;
- action_id;
- approval_id;
- evidence_id;
- capability_id;
- target/source refs.

## Redaction

Event payloads are safe metadata, not raw prompts, secrets, credentials, stdout dumps, or arbitrary provider payloads. Apply redaction before persistence.

## Metrics

Useful metrics include success/failure by terminal reason, model latency, tool latency, approval rates, evidence success, duplicate suppression, no-progress, budget exhaustion, and integration health. Do not count dispatch as successful evidence.

## Auditability

An operator must be able to reconstruct: what the model proposed, why it was accepted/rejected by deterministic policy, whether approval occurred, whether execution ran, and what evidence was produced.
