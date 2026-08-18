# ADR-0007 — Deterministic request and investigation pipeline

## Status

Accepted; amended after the semantic-primary cutover.

The investigation pipeline remains deterministic after a semantic plan is
validated. The superseded part of the original record is the requirement that
lexical code classify every request before any model call.

## Context

Infrastructure investigation needs repeatable safety, capability binding,
collection, evidence-validity, recovery, and budget rules. At the same time,
natural-language routing proved too brittle when deterministic regex/keyword
classification was the primary semantic interpreter.

## Decision

For RuntimeFactory-built agents, Orion uses a bounded model-planner/harness
boundary:

1. Narrow deterministic controls such as hard-safety/session operations may
   terminate locally; otherwise `SemanticPlannerAdapter` produces a typed
   semantic plan from the user request plus bounded semantic context.
2. `SemanticPlanHarnessValidator` validates the plan contract, read-only
   execution intent, target/source/freshness constraints, and other hard
   invariants. Invalid, malformed, or unavailable planning fails closed rather
   than falling through to lexical routing.
3. `SemanticPlanBinder` maps a validated semantic plan to the canonical
   `RequestFrame` and registered capability references. Capability details are
   disclosed/bound only as required rather than sending a complete registry on
   ordinary first turns.
4. Stable/general generation can be answered without collectors. Deterministic
   compute requests use the calculator contract. Current/external information
   is forced through the fixed Internet verification path.
5. Infrastructure inspection enters `ExecutionEngine`; `ExecutionPlanner` and
   `ExecutionGraphBuilder` produce the bounded DAG.
6. `ExecutionRuntime` dispatches nodes through `KnowledgeTool` and applies
   inspectors, preflight, retry, declared recovery, and shared budget policy.
7. `EvidenceMerge` preserves typed outcomes and Facts; completeness,
   reconciliation, and reviewed deterministic reasoning produce
   Findings/health state.
8. The model may explain bounded evidence. Final postconditions, semantic
   relevance verification, and at most one bounded response repair run before
   the single user-visible response.
9. Multi-intent requests use bounded typed semantic subplans with explicit
   dependencies; child execution remains isolated and subject to the same
   deterministic validation/execution boundaries.

Unsafe parameters, unsupported actions, unknown targets, invalid source
constraints, planner failure, and unavailable required evidence return bounded
clarification/refusal/failure outcomes. No failure grants the model a direct
tool API or revives regex-first primary routing.

## Consequences

- Natural-language interpretation is model-driven, while tool/command
  authorization remains deterministic.
- The model sees bounded semantic/evidence contracts rather than an unrestricted
  tool registry or execution API.
- Capability binding, recovery, evidence expansion, and stop conditions remain
  reproducible code paths.
- Planner/model failure can prevent a semantic request from running, but cannot
  widen execution authority.
- Insufficient evidence stays explicit and cannot trigger an unbounded
  model-controlled tool loop.

## Related records

- `ADR-0001-agent-responsibility-boundary.md`
- `ADR-0002-llm-assessment-only.md`
- `ADR-0003-knowledge-tool-single-entry-point.md`
- `ADR-0004-stateless-state-management.md`
- `ADR-0008-evidence-validity.md`
- `ADR-0010-deterministic-external-verification.md`
- `docs/ai/05_EXECUTION_PIPELINE.md`
