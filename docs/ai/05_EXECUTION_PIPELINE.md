# 05 - Execution Pipeline

This document describes the implemented deterministic request, collection, and
assessment flow.

## Boundary

Orion follows **Code investigates. AI explains.** Deterministic code owns
routing, target and source selection, parameters, capability selection,
execution, recovery, evidence validity, and reviewed rules. The assessment
model receives bounded evidence and has no command or tool authority.

```text
User request + session context
        |
        v
RequestFrame semantics and routing
   |             |                 |
   |             |                 +-> current/URL -> Internet verification
   |             +-> stable/general/generation -> model without collectors
   +-> infrastructure inspection
                    |
                    v
      target + parameters + source constraints
                    |
                    v
      evidence requirements + capability plan
                    |
                    v
      execution DAG -> KnowledgeTool -> Child Tool
                    |
                    v
      CommandResult -> CapabilityResult -> EvidencePackage
                    |
                    v
      completeness + Facts + Findings + health summary
                    |
          +---------+----------+
          |                    |
          v                    v
 DeterministicResponder   AssessmentRequest -> model
          |                    |
          +---------+----------+
                    v
       output guards + response + ExecutionTrace
```

Every handled request emits one credential-safe `ExecutionTrace` with stage
outcomes, routing status, resolved target and parameters, plan, evidence names,
answer strategy, model-usage reason, and safe failure information.

## Semantic routing

`RequestSemanticsClassifier`, `Normalizer`, and the session context build an
immutable `RequestFrame`. The frame distinguishes stable knowledge, live
environment inspection, current external information, explicit URLs, source
constraints, content generation, explanation, and mutation intent.

- Ambiguous semantics or missing required parameters produce deterministic
  clarification.
- Explicit unknown targets never fall back to `localhost`.
- Exact source constraints are enforced before capability dispatch and fail
  closed when the selected source cannot supply required evidence.
- Mutation requests are refused by the routing/safety boundary.
- Coordinated requests are decomposed into at most four ordered subframes and
  share target/time semantics where the request makes that relationship
  explicit.

## Infrastructure execution stages

1. `IntentResolver` and `TargetResolver` complete the request contract.
2. `EvidencePlanner`, `CapabilityPlanner`, `CapabilityResolver`, and
   `ParameterBinder` map the request to typed evidence and capability
   requirements.
3. `ExecutionPlanner` and `ExecutionGraphBuilder` build the dependency DAG.
4. `ExecutionRuntime` sends every node through `KnowledgeTool`, executes
   independent nodes in parallel, applies the shared budget and retry policy,
   and records runtime metrics.
5. `EvidenceMerge` retains structured failures, normalizes enabled outputs into
   Facts, reconciles conflicts, and runs `EvidenceCompleteness`.
6. Atomic thresholds and enabled reviewed composite rules produce source-linked
   Findings and a deterministic health summary.
7. `DeterministicResponder` answers supported fact/list/table requests;
   remaining requests use `AssessmentRequest` and the configured model.

Before model assessment, `EvidenceModelContextSerializer` converts the
assessment request into a deterministic byte/item-bounded context. It keeps
canonical facts, validity, missing/failure status, target/source identity, and
compact provenance. Contradictions are retained ahead of ordinary facts. Raw
provider payload is exposed only when `AssessmentRequest` explicitly requires
it for valid packages without canonical facts, through a separate bounded and
credential-redacted allowance.

## External verification

Requests classified as current/external use a fixed
`web_search -> deterministic select -> web_fetch -> evidence` flow. Explicit
public URLs can use fetch directly. Search and fetch share public-address
validation, redirect and DNS checks, time/size/tool-call budgets, short-lived
valid-only caching, and credential-safe provenance. A failed verification is
reported as unverified/unknown; model memory is not presented as current
evidence.

The optional semantic loop dispatches external-information plans through this
same executor. It does not send a semantic `web_search` capability directly to
the infrastructure execution engine. Explicit URLs therefore retain the same
public-address, redirect, DNS, timeout, and size checks.

## Structured calculation and final postconditions

Semantic plans can carry a typed `CalculatorRequest` for reviewed arithmetic
operations. The harness rejects missing, ambiguous, invalid, or conflicting
compute contracts. Successful requests execute once in `basic_calculator.py`
without a collector or assessment-model call, and the exact decimal result and
unit become the deterministic response.

Before a semantic-loop response reaches the public boundary,
`FinalResponseGuard` checks the validated target, live-verification status,
read-only boundary, deterministic calculator value, requested language/shape,
and cited provenance where those constraints are known. A violation produces a
safe deterministic replacement and a bounded trace record; it does not trigger
a model repair call.

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
