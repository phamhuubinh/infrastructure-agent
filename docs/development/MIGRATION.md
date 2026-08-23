# Migration Plan

> **Status at `259f85b`:** the configured Web/CLI Chat path has been cut over to the canonical
> model-driven runtime and the superseded deterministic/semantic routing stack has been removed from
> that configured hot path. This document remains the convergence plan for accepted target
> architecture that is not yet implemented everywhere. Do not use it as evidence that every phase
> is complete.
>
> One known remaining gap is Project knowledge/RAG: ADR-0003 defines it as a normal READ capability
> in the agent loop, while the current `src/tool/RAGTool/` service is still a separate Web workspace.

The goal is controlled replacement of the superseded architecture, followed by cleanup and
verification. Do not patch new language-specific cases into any compatibility path.

## Phase 1 — Contract first

Define and test readable canonical model/harness contracts:

- decision types;
- ACTION with capability, target, source, and typed arguments;
- observation contract;
- effect class;
- permission mode;
- event contract.

For the canonical Chat runtime, this foundation is implemented. Future changes must preserve the
same boundary rather than reintroducing prose routing.

## Phase 2 — Authority boundary

Authorization validates the model's structured proposal directly:

- exact capability lookup;
- exact target/source lookup;
- schema validation;
- READ/WRITE permission;
- approval scope;
- budgets and safety.

Natural-language hard constraints are not execution authority.

## Phase 3 — Dedicated agent runtime

The configured runtime follows:

```text
context -> model -> structured decision -> validate -> execute -> evidence -> model
```

The configured Web/CLI Chat composition no longer requires the superseded semantic planner/router
stack to decide what the user means.

## Phase 4 — Project/RAG integration

Expose active Project knowledge as a normal READ capability in the same agent loop while preserving
project/document isolation and efficient retrieval.

Keep useful retrieval implementation where it satisfies the new contract; change the boundary
before rewriting proven internals.

**Current gap at `259f85b`:** the Project RAG service is still a standalone Web
document-analysis workspace and is not registered as a Chat capability.

## Phase 5 — Session and dynamic evidence

Use bounded model context rather than lexical follow-up interpretation. Persist validated structured
references and timestamps, not language-specific semantic state machines.

Dynamic observations retain observation time and must not be silently represented as fresh.

## Phase 6 — Events and UI activity

Use structured request events as the common source for:

- UI activity timeline;
- request trace;
- `orion log` filtering;
- latency/failure diagnostics.

Do not expose private chain-of-thought.

## Phase 7 — WRITE path

Once READ behavior is stable, enforce WRITE capability classification and scoped ASK approvals.
Keep WRITE disabled for capabilities that have not been reviewed.

## Phase 8 — Remove legacy code

For each cleanup wave:

1. build a caller/import graph;
2. identify legacy modules with no required callers;
3. migrate still-valid responsibilities;
4. remove dead modules, tests, flags, adapters, and duplicate contracts;
5. search the repository for stale references;
6. run static/unit/integration validation appropriate to the change;
7. run live runtime QA as a separate explicit gate when requested.

The deterministic/semantic routing stack cleanup for the configured Chat hot path is complete at
`259f85b`. Do not recreate it for compatibility unless a concrete remaining caller proves a narrow
adapter is required.

## Phase 9 — Documentation and generated artifacts

After each convergence step:

- update root/operator/contributor documentation;
- regenerate OpenAPI when the API contract changes;
- update actual CLI/QA commands and configuration documentation;
- remove or clearly label migration-only statements;
- confirm each implementation claim against code/tests/runtime evidence.

## Rule during migration

Do not maintain two equal primary architectures. The canonical model-driven path is the configured
Chat architecture. Remaining gaps should converge toward accepted ADRs rather than restoring the
superseded semantic stack.
