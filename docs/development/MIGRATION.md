# Migration Plan

This documentation is intentionally written before the code refactor. The goal
is a controlled replacement of the primary architecture, followed by cleanup.

## Phase 1 — Contract first

Define and test the new readable model/harness contracts:

- decision types;
- ACTION with capability, target, source, and typed arguments;
- observation contract;
- effect class;
- permission mode;
- event contract.

Do not patch more language-specific cases in the old semantic path.

## Phase 2 — Authority boundary

Refactor validation so it authorizes the model's structured proposal directly:

- exact capability lookup;
- exact target/source lookup;
- schema validation;
- READ/WRITE permission;
- approval scope;
- budgets and safety.

Remove natural-language hard constraints from configured-agent authorization.

## Phase 3 — Dedicated agent runtime

Create the new configured runtime around:

```text
context -> model -> action -> validate -> execute -> evidence -> model
```

The configured composition root should no longer need the legacy semantic
planner/router stack merely to construct the agent.

## Phase 4 — Project/RAG integration

Expose active Project knowledge as a normal READ capability in the same agent
loop while preserving project/document isolation and efficient retrieval.

Keep the existing useful retrieval implementation where it satisfies the new
contract; change the boundary before rewriting proven retrieval internals.

## Phase 5 — Session and dynamic evidence

Replace lexical follow-up interpretation with bounded model context. Persist
validated structured references and timestamps, not language-specific semantic
state machines.

Implement recent-turn + compact-summary context and static/dynamic observation
handling.

## Phase 6 — Events and UI activity

Make structured request events the common source for:

- UI activity timeline;
- request trace;
- `orion log` filtering;
- latency/failure diagnostics.

## Phase 7 — WRITE path

Once READ runtime is stable, implement WRITE capability enforcement and scoped
ASK approvals. Keep WRITE disabled for capabilities that have not been reviewed
and classified.

## Phase 8 — Remove legacy code

Only after the new path is proven:

1. build a caller/import graph;
2. identify legacy modules with no required callers;
3. remove dead modules, tests, flags, adapters, and docs;
4. move still-useful components into their correct responsibility area;
5. remove duplicate concepts and compatibility shims;
6. run full static, unit, integration, runtime, and UI QA.

Likely legacy categories to reevaluate include semantic request classifiers,
lexical target/source/freshness/mutation parsing, old session semantic selectors,
legacy planners, and monolithic orchestration code. Do not delete tool/evidence
implementations merely because they were previously called by the old pipeline.

## Phase 9 — Documentation and generated artifacts

After code convergence:

- update root README and install/operator instructions;
- regenerate OpenAPI;
- document actual CLI commands and configuration;
- remove migration-only notes that are no longer useful;
- confirm every architecture claim is true in the runtime.

## Rule during migration

Do not maintain two equal primary architectures. The old path is compatibility
only; the new path becomes the configured primary path as soon as its required
contracts are complete.
