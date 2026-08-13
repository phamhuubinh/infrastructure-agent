# ADR-0004 — Execution state and session persistence

## Status

Accepted.

## Context

Infrastructure observations become stale quickly, while conversation turns and
resolved semantic context are useful for follow-up questions. Treating all
state as either permanent or forbidden would lose needed conversation behavior
or allow old operational data to influence a new investigation.

## Decision

Execution state is ephemeral. Commands, raw observations, execution plans and
graphs, runtime outputs, and model prompts are scoped to one investigation.

Session persistence is explicit and bounded:

- conversation stores persist user/assistant messages, title, timestamps,
  response timing, and compressed summaries;
- `SessionInvestigationContext` persists typed target, concept, service, path,
  time, incident, answer-shape, and prior-response metadata;
- the per-session evidence cache can reuse only fresh `VALID` or `VALID_EMPTY`
  packages under its key/TTL policy;
- raw tool output and execution state are not stored as conversation memory.

An explicit current target overrides inherited context. An unresolved explicit
target never falls back to an inherited target or `localhost`.

## Consequences

- Follow-ups can reuse supported semantics without treating earlier evidence as
  current.
- CLI/source Web sessions persist in SQLite and Compose sessions persist in
  PostgreSQL without changing the execution contract.
- Cache policy is visible and testable; failed, partial, stale, or contradictory
  evidence cannot become a successful cache hit.

## Related records

- `ADR-0001-agent-responsibility-boundary.md`
- `ADR-0007-deterministic-pipeline.md`
- `ADR-0008-evidence-validity.md`
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-007 and AD-008
