# 05 - Execution Pipeline

This document describes the implemented bounded reason/action controller,
deterministic execution boundary, and response-verification flow.

## Boundary

Orion's configured Agent v2 boundary is: **Model owns reasoning and next-action
selection. Harness owns authority, execution, evidence and completion.** The
controller can reason over the bounded request, context, summaries, selected
schema, and observations and choose its next structured decision. It never
receives direct command, arbitrary shell, or arbitrary HTTP authority.

```text
User request
        |
        v
Hard request constraints and bounded validated session context
        |
        v
Controller: reason -> disclose/discover -> validate -> execute -> observe -> reason
        |                                  |                 |
        |                                  |                 +-> typed compact observation
        |                                  v
        |                         reviewed runtime implementation
        |                         | host -> KnowledgeTool / Child Tool
        |                         | Internet -> ExternalVerificationExecutor / InternetTool
        |                         + calculator -> compute.deterministic
        v
deterministic completion/final boundaries -> response budget/sanitizer -> one response
```

Every handled request emits one credential-safe `ExecutionTrace`. Agent v2
traces contain bounded controller state/counts, action/observation/completion
metadata, and model-usage metadata. They exclude controller prompts, raw user
request in the Agent v2 public trace, raw action arguments, raw evidence or
command output, credentials, and hidden reasoning.

## Controller loop, disclosure, and execution

For normal RuntimeFactory-built CLI/Web agents,
`AgentControllerLoopCoordinator` with `ControllerAdapter` is the primary
natural-language interpreter. It receives the original request, narrow hard
constraints, bounded validated session context, and only fixed small
first-turn capability categories. It returns exactly one `FINAL`, `DISCOVER`,
`ACTION`, `CLARIFY`, or `REFUSE` decision.

Hard constraints are constructed before controller execution. Sensitive
disclosure and mutation requests can terminate before model, action, or tool
calls. Previously validated target/source context may be inherited, but an
explicit current target/source overrides stale state; acceptance and updates
remain deterministic. There is no silent target/source fallback and no default
localhost target.

Capability discovery is progressive rather than full-registry disclosure. A
`DISCOVER` decision reveals only the requested approved category as bounded
capability summaries; no capability executes. For an `ACTION`, the harness
discloses exactly the selected capability detail and typed schema when needed,
then the controller provides typed arguments. This schema handshake is not
execution. Optional context sections can be dropped by deterministic input
budgeting; observations remain compact and bounded.

`AgentActionValidator` treats each controller `ACTION` as untrusted structured
intent. It validates registered capability identity, typed parameters, exact
target/source authority, availability, read-only/safety constraints, and
budgets. Invalid actions return compact deterministic control feedback to the
controller; the harness performs no semantic repair or automatic retry. At
most one validated action executes for a turn. Controller, model, action, tool,
discovery, input, and completion-feedback limits bound the full loop.

`AgentActionExecutor` dispatches only validated approved capabilities. Linux,
Grafana, and Zabbix actions reach their existing `KnowledgeTool` and Child Tool
boundaries, which retain reviewed collection and command logic. Internet
actions use `ExternalVerificationExecutor` and `InternetTool`; bounded search
and fetch may occur internally, subject to source authority plus SSRF, DNS,
redirect, timeout, size, and tool-call controls. The calculator is the
first-class `compute.deterministic` Agent capability, not a Child Tool.

The reviewed runtime implementation returns typed outcomes. For ordinary host,
Grafana, and Zabbix actions, `AgentActionExecutor` packages the `ToolResult`
into an `EvidencePackage` through the existing `EvidenceMerge` packaging
boundary. Internet actions return verified action evidence; calculator actions
return a `CalculatorContractResult`. `AgentObservationSerializer` converts the
typed execution result into one compact observation with safe status, identity,
bounded facts/provenance, and control codes before the controller chooses
another decision. A configured v2 action does not automatically run the full
legacy completeness, Findings, or health-reasoning pipeline.

## Completion and final response

A controller `FINAL` candidate remains untrusted model prose.
`CompletionCheck` deterministically evaluates the hard constraints and compact
observations: refusal/read-only status, target/source/URL identity, required
fresh/current evidence, calculator consistency, execution claims, and evidence
sufficiency. It reuses `FinalResponseGuard` only for the calculator exact-value
invariant, not as the complete Agent v2 final-response pipeline. A rejected
candidate becomes compact deterministic control feedback for another bounded
controller round; an accepted candidate becomes the terminal controller result.

The existing compatibility/public boundaries then apply: parse-only
artifact/config validation when applicable, output sanitizer, response budget,
and API-safe trace/public projection. They deliver one final public response.

`SemanticRelevanceVerifier` and `SemanticResponseRepairer` remain part of the
legacy semantic-loop finalization path. That path can perform its bounded
relevance check and one repair cycle; configured Agent v2 controller FINALs do
not automatically construct or invoke either component.

## Model usage telemetry

`ModelUsageRecorder` keeps normalized per-request call metadata for controller,
response, relevance, and repair calls when those operations are used.
Provider-reported input tokens, reasoning
tokens, visible-output tokens, and total-output tokens remain distinct from the
character-derived `estimated_input_tokens`; unsupported/unknown values stay
`null`, never fabricated as zero. Configured reasoning effort is recorded
separately from actual provider reasoning-token usage.

The existing trace/model-usage machinery also records terminal controller state,
decision counts, discovery and action counts (proposed/validated/rejected/
executed), separate tool and calculator calls, observation summaries,
completion reasons, rounds/stop reason, bounded capability/target/source IDs,
and retained/dropped context metadata. These are observability fields, not
performance SLAs.

Per-purpose aggregates use strict unknown propagation: if any call of a purpose
lacks a field, that aggregate field remains unknown instead of presenting a
partial sum as exact. At most 16 per-call entries are serialized; excess calls
are counted in `dropped_calls`. Prompts, credentials, and hidden reasoning text
are never stored. `/api/query` applies an additional bounded/redacted projection
before exposing `execution_trace`.

## Result contracts

`CommandResult` is the immutable backend outcome. It contains status, exit
code, separate stdout/stderr, error type, safe command/target metadata,
duration, and redacted serialization. `SUCCESS` and `EMPTY_SUCCESS` are the
only command-success states.

`CapabilityResult` is the Child Tool outcome. `VALID` and `VALID_EMPTY` are the
only successful statuses. `PARTIAL`, `COLLECTION_FAILED`, `UNSUPPORTED`,
`INVALID_PARAMETERS`, and `PARSE_FAILED` retain safe diagnostics but cannot
satisfy required evidence. Failures carry stable code, category, and
recoverability metadata.

`EvidencePackage` retains the structured capability result, source,
parameters, timeframe, warnings, failures, command provenance, Facts, recovery
records, and bounded raw data. A package is reusable only when it is fresh and
its status is `VALID` or `VALID_EMPTY`.

No stage converts collection failure into a zero, empty collection, or missing
value that looks like a measurement.

## Facts, Findings, and bounded recovery

A `Fact` contains subject, dotted metric, value, unit, observation and
collection times, source, target, validity, freshness, confidence, dimensions,
and `Provenance`. `FactReconciler` marks incompatible same-scope observations
as contradictory.

Reviewed atomic and composite rules produce `Finding` records with rule
identity/version, decision, score/coverage/confidence, supporting and
contradicting Fact IDs, missing metrics, and source links.

These Facts, Findings, rules, recovery, and expansion components remain current
where the existing deterministic investigation pipeline is explicitly used;
they are not implicit work performed after every configured Agent v2 action.

`CapabilityRecovery` can use only alternatives declared in capability
metadata, only for recoverable errors, to a maximum depth of two and within the
shared `ExecutionBudget`. `EvidenceExpander` can add one bounded
missing-evidence round. The model cannot request either operation.

## Current feature switches

`FeatureFlagStore` reads an optional file selected by
`ORION_FEATURE_FLAGS_FILE`; when no file exists it uses
`FeatureFlagsConfig` defaults. Environment variables override individual
fields. Structured command exposure, canonical Fact exposure, composite rules,
and claim grounding default to disabled. General-agent routing, external
verification, web search, and source constraints default to enabled. The
legacy general-agent routing flag is a compatibility control; RuntimeFactory
wires the Agent v2 controller as the primary natural-language path. The
read-only action boundary remains mandatory regardless of these switches.

The runtime still accepts tuple-unpacked `CommandResult` and raw Child Tool
payloads through explicit deprecated compatibility adapters. Current code uses
the named structured contracts at the primary runtime boundaries.

## Related documents

- `06_TOOL_AND_CAPABILITY_DESIGN.md`
- `docs/adr/ADR-0008-evidence-validity.md`
- `docs/adr/ADR-0009-deterministic-reasoning-v1.md`
- `docs/adr/ADR-0010-deterministic-external-verification.md`
- `docs/troubleshooting.md`
