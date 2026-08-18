# ADR-0001 — Agent responsibility boundary

## Status

Accepted; amended after the semantic-primary cutover.

The original decision that model output must not gain infrastructure authority
still applies. What changed is ownership of natural-language interpretation:
the bounded model planner is now the primary semantic interpreter, while the
harness remains authoritative for validation and execution.

## Context

Orion must understand general requests, execute infrastructure investigations,
and produce responses without turning model output into infrastructure
authority. The runtime therefore needs an explicit boundary between semantic
planning, deterministic validation, execution, evidence collection, and model
response generation.

## Decision

`DeterministicAgent` remains the request/response orchestrator. For
RuntimeFactory-built agents it invokes a bounded `SemanticPlannerAdapter` for
primary natural-language interpretation, carries bounded session context,
coordinates the semantic loop, selects response paths, and emits traces.

A semantic plan may propose a route/domain, execution intent, target reference,
source/freshness constraints, concept, deterministic-compute/clarification
state, and bounded subplans. Those fields are advisory until deterministic
harness validation succeeds. Planner failure or malformed output fails closed;
it does not fall back to the legacy lexical router.

The harness owns read-only and hard-safety enforcement, target/source
validation, capability binding, budgets, evidence/provenance requirements,
deterministic compute/reasoning, and final hard postconditions.
`ExecutionEngine` owns infrastructure investigation: it compiles and runs the
bounded execution DAG, merges evidence, evaluates implemented deterministic
rules, and returns an `InvestigationRequest`.

The model has no direct tool, command, retry, recovery, or mutable execution
API. Model-proposed target/source semantics do not grant authority by
themselves. Child Tools execute only registered capabilities with validated
typed parameters. Model calls for direct responses, evidence assessment,
semantic relevance checking, and the bounded repair pass remain tool-less.

## Consequences

- Semantic interpretation can improve with the configured model without moving
  execution authority out of deterministic code.
- Model replacement can change interpretation quality, but cannot bypass
  read-only policy, registry validation, evidence requirements, or budgets.
- Infrastructure execution remains reproducible from the validated plan,
  configuration, environment, and evidence.
- Session context can influence planning but never substitutes old tool output
  for current evidence.
- Compatibility lexical routing may remain behind explicit no-planner/direct
  construction surfaces, but it is not the RuntimeFactory primary path.

## Related records

- `ADR-0002-llm-assessment-only.md`
- `ADR-0003-knowledge-tool-single-entry-point.md`
- `ADR-0004-stateless-state-management.md`
- `ADR-0007-deterministic-pipeline.md`
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-017
