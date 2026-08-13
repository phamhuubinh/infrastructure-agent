# ADR-0002 — Model has no investigation authority

## Status

Accepted.

## Context

Orion supports infrastructure investigation, current external verification,
stable general requests, and content generation. Tool access must remain
auditable and independent of model output.

## Decision

The model has two tool-less interfaces:

- `assess(AssessmentRequest)` interprets bounded collected evidence and
  deterministic Findings.
- `assess_raw(prompt)` handles separately routed stable/general requests and
  content generation.

The model does not receive a tool registry, backend, command API, mutable
execution context, or permission to choose targets, capabilities, queries,
URLs, retries, recovery, or evidence expansion. Those decisions are
deterministic code paths completed before assessment.

`AssessmentModelAdapter` is the model boundary. Implementations consume the
pipeline-owned `AssessmentRequest` data contract but have no dependency on
Child Tool implementations or runtime dispatch objects. Linux command
templates remain in reviewed capabilities and accept only validated typed
parameters.

The read-only action-claim guard remains mandatory. Evidence-grounding,
numeric, and language guards apply according to the current claim-guard
configuration, and `/api/query` applies the final hidden-reasoning/language/
non-empty response sanitizer.

When no model is configured, `UnconfiguredAssessmentAdapter` reports setup
mode. `MockAssessmentAdapter` supplies deterministic test behavior.

## Consequences

- Model selection cannot change collection or safety authority.
- Infrastructure routing and evidence collection are testable without an LLM.
- Prompts contain evidence and response context rather than tool schemas.
- Incomplete evidence is reported explicitly; the model cannot start another
  collection loop.

## Related records

- `ADR-0001-agent-responsibility-boundary.md`
- `ADR-0003-knowledge-tool-single-entry-point.md`
- `ADR-0007-deterministic-pipeline.md`
- `ADR-0008-evidence-validity.md`
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-002 and AD-011
