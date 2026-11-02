# ADR 0016 — Single runtime redesign and backlog reset

## Status

Current target decision, 2026-10-29, following the user's request to redesign
Orion and retire the old issue backlog. Amended later the same day by
[ADR 0017](0017-windows-linux-command-focus.md), which prioritizes Windows/Linux
commands and retires dedicated monitoring adapters. The documentation set expresses this
target; implementation correctness is tracked separately.

## Decision

Use one main model/runtime plus tools/skills. Chat, Projects and Remote Control
are product surfaces with distinct data scope, not independent AI agents.
Projects hold context, instructions, documents and history; remote machines are
model-free workers/connections. Device Chat reuses ChatRuntime with server-owned
endpoint binding and no Project/ordinary Chat data.

The [consolidated baseline](../architecture/BASELINE_2026-10-29.md) defines the
whole product boundary. Preserve compatible detailed contracts from ADRs 0001–0015:

- direct first-model-turn canonical registry schemas, no semantic pre-router or
  manual tool picker;
- provider-neutral model interface and application-owned scope;
- conversation mutation modes, optional server ceiling and independent worker
  policy;
- portable temporary workers as primary, remembered mode as explicit optional;
- no automatic replay of dispatched ambiguous mutations;
- scoped document retrieval and untrusted external evidence.

The [skill contract](../architecture/SKILLS.md) adds reusable task guidance to the
target design without inventing another runtime or claiming a current loader.
Scheduler/MCP/worker modules already exist and should be verified/reused, not
discarded because the product no longer needs separate agents.

## Scope of supersession

This decision supersedes product plans requiring separate AI agents, requiring
installed/persistent workers for customer use, or duplicating runtimes by surface.
Subject to ADR 0017 replacing the no-shell/dedicated-monitoring requirements,
this decision preserves compatible permission contracts, platform
limitations, packaging rules or existing remembered-worker support. ADR 0007
continues to supersede retired progressive schema exposure; ADR 0014 continues to
supersede the earlier absent-allowlist mutation-denial rule.

## Consequences and evidence

Keep the present Python backend, TypeScript UI, SQLite/blob persistence and model
adapters unless implementation evidence justifies a separate change. This is a
documentation redesign, not a destructive rebuild or a statement that every
existing component is production-ready.

The [implementation inventory](../development/IMPLEMENTATION_STATUS.md) records
inspected source. [Reconciliation](../development/REBUILD_GUIDE.md) and
[acceptance](../development/ACCEPTANCE_CRITERIA.md) guide future implementation.

Issue #162 was closed as not_planned for a planning reset, not verified completion.
See the [reset record](../development/GITHUB_RESET_2026-10-29.md). Local working
documentation has not been committed or pushed by this task.
