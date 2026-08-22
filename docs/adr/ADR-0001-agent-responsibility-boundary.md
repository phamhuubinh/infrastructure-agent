# ADR-0001 — Agent responsibility boundary

## Status

Accepted; amended after the Agent v2 controller cutover.

The original decision that model output must not gain infrastructure authority
still applies. The configured primary natural-language path is now the bounded
Agent v2 controller, while the harness remains authoritative for validation,
execution, evidence, and completion.

## Context

Orion must understand general requests, execute infrastructure investigations,
and produce responses without turning model output into infrastructure
authority. The runtime therefore needs an explicit boundary between semantic
planning, deterministic validation, execution, evidence collection, and model
response generation.

## Decision

`DeterministicAgent` remains the request/response orchestrator. For configured
RuntimeFactory-built agents it invokes `AgentControllerLoopCoordinator` and
`ControllerAdapter` for primary natural-language interpretation, carries
bounded session context, selects response paths, and emits traces. The current
boundary is: **Model owns reasoning and next-action selection. Harness owns
authority, execution, evidence and completion.**

The controller returns exactly one structured `FINAL`, `DISCOVER`, `ACTION`,
`CLARIFY`, or `REFUSE` decision. It may select a registered capability ID and
typed arguments after bounded discovery and selected-schema disclosure. Those
fields are advisory until `AgentActionValidator` validates them. Controller
failure or malformed output fails closed; it does not fall back to the legacy
lexical router.

The harness owns hard request constraints, read-only and hard-safety
enforcement, target/source validation, progressive capability disclosure,
action validation and dispatch, budgets, evidence/provenance requirements,
deterministic compute, and final hard postconditions.
`ExecutionEngine` owns infrastructure investigation: it compiles and runs the
reviewed execution work, merges evidence, and evaluates implemented
deterministic rules. Linux/Grafana/Zabbix actions retain the `KnowledgeTool` /
Child Tool boundary; Internet uses `ExternalVerificationExecutor` /
`InternetTool`; `compute.deterministic` is first-class rather than a Child Tool.

The model has no direct tool, arbitrary command, arbitrary HTTP, recovery, or
mutable execution API. Model-selected target/source/action semantics do not
grant authority by themselves. `AgentActionExecutor` dispatches only registered
capabilities with validated typed parameters. Invalid actions return compact
control feedback; harness code does not automatically repair/retry them.
Model calls for direct responses, evidence assessment, semantic relevance
checking, and the bounded repair pass remain tool-less.

## Consequences

- The controller can choose the next bounded action with the configured model
  without moving execution authority out of deterministic code.
- Model replacement can change interpretation quality, but cannot bypass
  read-only policy, registry validation, evidence requirements, or budgets.
- Infrastructure execution remains reproducible from the validated action,
  configuration, environment, and evidence.
- Session context can influence controller reasoning but never substitutes old
  tool output for current evidence.
- Compatibility semantic-planner and lexical routing code may remain behind
  explicit setup/no-controller/direct construction surfaces, but is not the
  RuntimeFactory primary path.

## Related records

- `ADR-0002-llm-assessment-only.md`
- `ADR-0003-knowledge-tool-single-entry-point.md`
- `ADR-0004-stateless-state-management.md`
- `ADR-0007-deterministic-pipeline.md`
- `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-017
