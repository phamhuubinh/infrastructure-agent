# Testing strategy

## Test pyramid

### Contract tests

Prove exact serialization, closed schemas, capability registration, authority decisions, evidence records, event contracts, and provider normalization.

### Runtime tests with fake model/executor

Cover complete loops without external systems:

- direct final;
- capability search → exposed tool → tool call → evidence → final;
- invented/unexposed tool rejected;
- malformed arguments rejected before executor;
- exact target/source enforcement;
- permission allow/ask/deny;
- approval fingerprint binding;
- budget exhaustion;
- duplicate successful call not redispatched;
- no-progress termination;
- evidence-reference validation.

### Executor tests

Per integration, test argument binding, least-privilege routing, failure normalization, bounded outputs, result schema, and evidence projection.

### Persistence tests

Failure injection for transaction/recovery behavior, concurrent delete/clean, corruption preservation, and resume semantics.

### API/UI tests

Typed timeline, approvals, evidence, semantic health, cancellation, and session isolation.

## Live-model gates

Fake tests cannot prove model usability. Use narrow live probes only after static contracts are green.

Mandatory first live probes after runtime cutover:

1. exact arithmetic: one tool execution, evidence, correct final;
2. different arithmetic input to rule out memorized prompt behavior;
3. model identity grounded from configuration;
4. protected-instruction refusal;
5. read-only infrastructure capability;
6. write requiring approval.

Trace first real failure only. Do not shotgun-fix cascades.

## Release acceptance

See `ACCEPTANCE_CRITERIA.md`.
