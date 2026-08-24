# Migration Plan

> GitHub `main` at `3e88075` uses canonical model-driven Web/CLI Chat construction. This is not complete target convergence. The current defect/convergence ledger is `IMPLEMENTATION_GAPS.md`.

## Phase 1 — Canonical contracts

Readable decisions/actions/observations/effects/permissions/events/provider-neutral model boundary. Current follow-up: enforce active stage/schema and actual disclosure state after parsing.

## Phase 2 — Authority

Validate legal stage, exact disclosed capability, target/source, arguments, effect/permission/approval, budget/safety, and fail-closed configuration.

## Phase 3 — Runtime/completion

```text
bounded context -> model -> stage-validated decision -> authority -> execution -> evidence -> model -> evidence-aware completion
```

Add no-progress detection for invalid-decision cycles and objective final-claim validation.

## Phase 4 — Project/RAG

Expose Project knowledge as a normal READ capability. Keep current standalone Web workspace until integrated, but harden its standalone network/SSRF/auth boundary independently.

## Phase 5 — Sessions/context/persistence

Aggregate context budget + summary retention + dynamic evidence timestamps + consistent SQLite/PostgreSQL management + lifecycle-safe delete/query + corrupt-store fail-closed + transactional/recoverable document/project mutation.

## Phase 6 — Events/metrics/UI

Wire one structured event stream for UI timeline, traces, CLI diagnostics, and metrics.

## Phase 7 — WRITE

Reviewed WRITE capabilities + scoped ASK approvals.

## Phase 8 — Remove dead legacy code

Caller/import/config/persistence proof → migrate still-valid deterministic safety/evidence responsibilities → delete unreachable semantic modules/flags/tests/state. Never reconnect legacy semantic routing to pass tests.

## Phase 9 — Product/runtime correctness

Resolve model-health/identity, generation/session isolation, attachments, destructive confirmations, safe headers, CI, and all remaining `IMPLEMENTATION_GAPS.md` items.

## Phase 10 — Docs/generated artifacts

Mark/remove resolved gap entries, regenerate OpenAPI when contracts change, update actual CLI/QA/config docs, confirm current claims against code/tests/runtime evidence.
