# Rebuild acceptance criteria

The rebuild is complete only when all critical invariants are demonstrated.

## Architecture

- One runtime serves CLI and Web/API.
- Model protocol is tool calls/results; no legacy ACTION_DETAIL/OBSERVATION/FEEDBACK FSM remains.
- One canonical CapabilityDefinition drives schema, authority, executor binding and result/evidence behavior.
- One event stream is the observability truth.

## Model/tool usability

- Exact arithmetic produces exactly one calculator execution and correct evidence-backed final.
- A second different arithmetic query also passes.
- Model can discover and call a host/integration read capability without inventing refs.
- Repeated identical successful tool calls do not redispatch.

## Authority/security

- Unexposed capability cannot execute.
- Unknown capability cannot execute.
- Missing/extra/invalid arguments cannot execute.
- Unknown target/source cannot execute.
- No implicit localhost/source fallback.
- Write action follows configured ask/deny/allow policy.
- Approval binds to exact action fingerprint.
- Secrets do not appear in model context, public events, evidence or UI.
- Required isolation failing to initialize blocks execution.

## Evidence

- Execution attempt is distinct from success.
- Every reported successful objective action has evidence.
- Model references evidence IDs; evidence identity/provenance is harness-owned.
- Stale/partial/error evidence is represented honestly.

## Persistence/recovery

- session/project deletion cannot be resurrected by in-flight work;
- corruption is preserved/quarantined;
- multi-store document operations recover after injected failures.

## Quality gates

- focused and full local unit/static suite green;
- lint/type checks green;
- generated OpenAPI matches implementation;
- Docker integration passes;
- narrow live-model probes pass;
- smoke QA passes before broader release suite.
