# Authority, permission, approval, and budget

These concepts are deliberately separate.

## Authority

Authority answers: **Is this exact proposed action a valid action Orion knows how to authorize?**

Validation order:

1. tool was exposed;
2. capability exists and is available;
3. arguments match the capability's closed schema;
4. target/source presence matches capability applicability;
5. target/source IDs exist exactly;
6. target/source kinds match capability policy;
7. effect and runtime binding match reviewed metadata;
8. safety review is valid.

No natural-language fallback is allowed.

## Permission

Permission answers: **May this actor/session/request perform this class of action?**

Recommended outcomes:

- `allow` — execute without interrupting;
- `ask` — require explicit approval;
- `deny` — do not execute.

Default policy:

- safe local/meta discovery: allow;
- read-only infrastructure queries: allow when target/source access is configured;
- writes: ask by default;
- destructive/high-impact operations: ask or deny according to policy;
- unknown/unreviewed capability: deny.

## Approval

Approval is a human or managed-policy decision for one proposed action or a narrowly defined scope. Approval must bind to the canonical action fingerprint, not a prose description alone.

Approval record should include:

- approval ID;
- action fingerprint;
- capability ID;
- target/source refs;
- effect/risk;
- requester/session;
- expiry/scope;
- decision and decision source.

Changing arguments, target, source, or capability invalidates the approval.

## Budget

Budgets bound autonomous work even when individual calls are allowed.

Track at least:

- model calls;
- tool-search calls;
- tool proposals;
- executions;
- write executions;
- external network calls/bytes when relevant;
- elapsed wall time;
- repeated/no-progress actions.

Do not increase limits to hide deterministic loops.

## Important separation

Permission/approval is not sandboxing. A permitted action can still run inside a restricted execution environment. Conversely, a sandbox does not make an unauthorized action acceptable.
