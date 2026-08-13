# ADR-0001 — Agent responsibility boundary

## Status

Accepted; aligned with the deterministic pipeline in ADR-0007.

## Context

Orion must route general requests, execute infrastructure investigations, and
produce responses without giving an assessment model infrastructure authority.
The runtime therefore needs an explicit boundary between orchestration,
execution, evidence collection, and model assessment.

## Decision

`DeterministicAgent` is the request/response orchestrator. It owns semantic
routing, bounded session context, deterministic clarification/refusal,
selection between deterministic response and assessment, and response traces.

`ExecutionEngine` owns infrastructure investigation. It resolves the evidence
contract, compiles and runs the execution DAG, merges evidence, evaluates
implemented deterministic rules, and returns an `InvestigationRequest`.

The Agent and engine do not accept model-generated commands, capabilities,
targets, retries, or recovery decisions. Child Tools execute only registered
capabilities with validated parameters. The assessment model receives a
bounded request after evidence collection and writes an explanation; general
chat uses the separate raw-assessment interface without tool access.

## Consequences

- Collection and safety behavior is independent of the selected model.
- Model replacement does not change tool authority.
- Infrastructure requests are reproducible from request, configuration,
  environment, and evidence.
- Session context can influence semantic resolution but never substitutes old
  tool output for current evidence.

## Related records

- `ADR-0002-llm-assessment-only.md`
- `ADR-0003-knowledge-tool-single-entry-point.md`
- `ADR-0004-stateless-state-management.md`
- `ADR-0007-deterministic-pipeline.md`
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-017
