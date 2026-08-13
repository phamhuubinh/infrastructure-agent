# ADR-0007 — Deterministic request and investigation pipeline

## Status

Accepted.

## Context

Infrastructure investigation uses repeatable routing, safety, collection, and
evidence-validity rules. Model-directed iteration would make target selection,
tool choice, cost, and failure behavior non-reproducible.

## Decision

Orion routes every request deterministically before any model or tool call.

1. Request semantics and session context produce an immutable `RequestFrame`.
2. Stable/general and generation requests bypass infrastructure collectors.
3. Current external information and explicit public URLs use the fixed
   deterministic Internet verification path.
4. Infrastructure inspection resolves intent, target, typed source
   constraints, parameters, evidence requirements, and capability references.
5. `ExecutionPlanner` and `ExecutionGraphBuilder` produce a bounded DAG.
6. `ExecutionRuntime` dispatches every node through `KnowledgeTool` and applies
   inspectors, preflight, retry, recovery, and budget policy.
7. `EvidenceMerge` preserves typed outcomes and enabled Facts; completeness,
   reconciliation, and reviewed reasoning produce Findings/health state.
8. `DeterministicResponder` handles supported simple answers. Remaining
   infrastructure answers use one assessment request; general chat uses the
   separate tool-less raw-assessment path.

Ambiguity, unsafe parameters, unsupported actions, unknown targets, and exact
source unavailability return deterministic clarification/refusal/failure. They
do not fall back to model planning.

## Consequences

- Tool and command selection is reproducible and testable without a model.
- The model sees bounded evidence instead of tool schemas or execution plans.
- Bounded multi-intent decomposition, recovery, and evidence expansion remain
  deterministic code paths.
- Insufficient evidence stays explicit and cannot trigger a model-controlled
  tool loop.

## Related records

- `ADR-0001-agent-responsibility-boundary.md`
- `ADR-0002-llm-assessment-only.md`
- `ADR-0003-knowledge-tool-single-entry-point.md`
- `ADR-0004-stateless-state-management.md`
- `ADR-0008-evidence-validity.md`
- `ADR-0010-deterministic-external-verification.md`
- `docs/ai/05_EXECUTION_PIPELINE.md`
