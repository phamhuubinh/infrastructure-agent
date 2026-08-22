# ADR-0002 — Model has no investigation authority

## Status

Accepted; amended after the Agent v2 controller cutover.

The phrase "no investigation authority" means no authority to execute or
authorize infrastructure effects. It no longer means that every semantic
decision is made before the model is called.

## Context

Orion supports infrastructure investigation, current external verification,
stable general requests, and content generation. Semantic understanding needs
model flexibility, while tool access and operational authority must remain
auditable and independent of free-form model output.

## Decision

Model-facing operations are bounded and tool-less:

- `ControllerAdapter` obtains one structured `FINAL`, `DISCOVER`, `ACTION`,
  `CLARIFY`, or `REFUSE` decision from the configured model connection/fallback
  chain.
- `AssessmentModelAdapter` produces bounded direct responses or interprets
  collected evidence and deterministic Findings.
- semantic relevance verification and the single bounded repair pass operate
  on response contracts; they do not receive execution authority.

The controller may choose the next registered capability and typed arguments
after bounded discovery or selected-schema disclosure. Deterministic harness
code validates those proposals, enforces exact target/source authority,
read-only/safety and budgets, and decides whether execution is permitted.

The model does not receive a backend command API, arbitrary HTTP API, mutable
execution context, or permission to bypass registry validation, choose
arbitrary commands, authorize a target, control arbitrary retries/recovery, or
extend evidence collection outside the bounded harness. The controller may make
the next approved selection after a compact observation, but
`AgentActionValidator` and `AgentActionExecutor` remain authoritative. Linux
command templates remain in reviewed capabilities and accept only validated
typed parameters.

Provider clients can be shared safely between planner/assessment operations,
but conversation/session state is not stored in those clients. Prompts and
traces do not contain credentials or hidden reasoning text.

The final response still passes deterministic language, artifact, repetition,
claim/postcondition, and API sanitization boundaries as applicable.

When no model is configured, RuntimeFactory installs setup-mode planner/model
adapters. Deterministic hard-safety refusals and model-management/health paths
remain available, but semantic requests do not revive regex-first live routing.

## Consequences

- Model selection can change bounded next-action selection and prose quality,
  but not collection or safety authority.
- The controller can express user intent and select approved actions without a
  general tool-calling interface.
- Capability validation, execution, evidence validity, deterministic recovery,
  and stop conditions remain deterministic and testable.
- Incomplete evidence stays explicit; the model cannot open an unbounded
  collection loop.

## Related records

- `ADR-0001-agent-responsibility-boundary.md`
- `ADR-0003-knowledge-tool-single-entry-point.md`
- `ADR-0007-deterministic-pipeline.md`
- `ADR-0008-evidence-validity.md`
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-002 and AD-011
