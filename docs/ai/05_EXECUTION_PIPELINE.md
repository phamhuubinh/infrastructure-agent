# 05 - Execution Pipeline

This document describes the implemented semantic-planning, deterministic
validation/collection, and response-verification flow.

## Boundary

Orion still follows **Code investigates. AI explains.** as the execution
boundary, with one important qualification: AI now interprets natural-language
requests into a bounded advisory semantic plan before code investigates.
Deterministic code decides whether that plan is valid, which registered
capabilities may execute, how evidence is collected, and whether the final
response satisfies hard postconditions. The model never receives a direct
command or tool API.

```text
User request + bounded session context
        |
        v
SemanticPlannerAdapter (model; typed advisory SemanticPlan)
        |
        v
SemanticPlanHarnessValidator
   |             |                    |
   |             |                    +-> multi-intent -> 2-4 child subplans
   |             +-> direct/compute -> no infrastructure collectors
   +-> capability-assisted
                    |
                    v
             SemanticPlanBinder
          |                       |
          v                       v
 infrastructure RequestFrame   current/external RequestFrame
          |                       |
          v                       v
   ExecutionEngine       ExternalVerificationExecutor
          |                       |
          +-----------+-----------+
                      v
        evidence / Facts / Findings / calculation
                      |
           +----------+----------+
           |                     |
           v                     v
 deterministic response     bounded model response
           |                     |
           +----------+----------+
                      v
       FinalResponseGuard -> relevance check when applicable
                      |
          at most one bounded repair + one re-verification
                      |
                      v
       response budget + output sanitizer + ExecutionTrace
```

Every handled request emits one credential-safe `ExecutionTrace`. Semantic-loop
traces contain bounded planner/validation/binding/state information, execution
counters, postconditions, and model-usage metadata; they do not contain model
prompts, credentials, hidden reasoning, or raw evidence payloads.

## Semantic planning and validation

For normal RuntimeFactory-built CLI/Web agents, `SemanticPlannerAdapter` is the
primary natural-language interpreter. `RequestSemanticsClassifier` and the
legacy `_route_request()` path remain compatibility surfaces for explicitly
constructed no-planner agents; planner-configured requests do not fall through
to them on failure.

The first-pass planner prompt is deliberately small. It contains the current
request, a bounded allowlist of relevant session fields, the semantic response
schema, and fixed authority instructions. It contains no commands, credentials,
tool schemas, capability details, evidence, or hidden reasoning. The planner
can propose route/domain, execution intent, target reference,
source/freshness constraints, concept, clarification state, deterministic
compute, and bounded subplans.

`SemanticPlanHarnessValidator` treats that plan as untrusted input:

- mutation intent and unsafe/unsupported plan shapes fail closed;
- target references are checked against the target registry, with no implicit
  localhost inheritance for an environment child that requires an explicit
  target;
- exact source constraints/exclusions and freshness are normalized and
  validated before dispatch;
- structured calculator contracts are validated before deterministic compute;
- multi-intent plans are limited to 2-4 non-recursive child plans, and a child
  may depend only on earlier children.

Planner provider failover is bounded to one call per configured provider.
There is no planner repair/retry loop. A failed, malformed, uncertain, or
unsupported plan terminates with a bounded response rather than reviving the
old regex-first routing path.

## Capability disclosure and binding

The first-pass planner does not receive a capability registry. The repository
implements separate lazy disclosure contracts:

- `CapabilitySummaryIndex` holds compact provider-neutral records containing an
  ID, purpose, source family, target kind, data kind, and availability; these
  summaries contain no commands or parameter schemas and can be filtered to a
  capability-assisted plan.
- `LazyCapabilityDetailExpander` expands exactly one selected capability ID
  only after semantic validation succeeds. Unknown, unavailable, or
  source-blocked selections return structured failure and the expander never
  searches for an alternative capability.

The current primary `SemanticPlanBinder` does not feed expanded detail back to
the planner. After harness validation it reuses `EvidencePlanner`,
`CapabilityResolver`, and `ParameterBinder` to create the canonical
`RequestFrame`, bind registered `CapabilityReference` values, validate typed
parameters, and build the existing execution plan.

## Infrastructure execution stages

1. `SemanticPlanBinder` converts a harness-validated capability-assisted plan
   into the canonical `RequestFrame` and existing typed evidence/capability
   requirements. Target, source, and parameter checks still run in code.
2. `ExecutionPlanner` and `ExecutionGraphBuilder` build the dependency DAG.
3. `ExecutionRuntime` sends every node through `KnowledgeTool`, executes
   independent nodes in parallel, applies the shared budget and retry policy,
   and records runtime metrics.
4. `EvidenceMerge` retains structured failures, normalizes enabled outputs into
   Facts, reconciles conflicts, and runs `EvidenceCompleteness`.
5. Atomic thresholds and enabled reviewed composite rules produce source-linked
   Findings and a deterministic health summary.
6. `DeterministicResponder` handles supported deterministic answers; remaining
   evidence-backed responses use `AssessmentRequest` and the configured model.

Before model assessment, `EvidenceModelContextSerializer` converts the
assessment request into a deterministic byte/item-bounded context. It keeps
canonical facts, validity, missing/failure status, target/source identity, and
compact provenance. Contradictions are retained ahead of ordinary facts. Raw
provider payload is exposed only when `AssessmentRequest` explicitly requires
it for valid packages without canonical facts, through a separate bounded and
credential-redacted allowance.

## External verification

A harness-validated plan whose domain/freshness requires current external
information uses the fixed `web_search -> deterministic select -> web_fetch ->
evidence` flow. Explicit public URLs can use fetch directly. Search and fetch
share public-address validation, redirect and DNS checks, time/size/tool-call
budgets, short-lived valid-only caching, and credential-safe provenance. A
failed verification is reported as unverified/unknown; model memory is not
presented as current evidence.

The semantic loop dispatches these plans through `ExternalVerificationExecutor`;
it does not hand a semantic `web_search` capability or URL-selection API to the
model. Explicit URLs therefore retain the same public-address, redirect, DNS,
timeout, and size checks.

## Structured calculation and final postconditions

Semantic plans can carry a typed `CalculatorRequest` for reviewed arithmetic
operations. The harness rejects missing, ambiguous, invalid, or conflicting
compute contracts. Successful requests execute once in `basic_calculator.py`
without a collector or assessment-model call, and the exact decimal result and
unit become the deterministic response.

Before a semantic-loop response reaches the public boundary,
`FinalResponseGuard` checks the validated target, live-verification status,
read-only boundary, deterministic calculator value, requested language/shape,
and cited provenance where those constraints are known. Failed checks first
produce a safe deterministic replacement plus bounded violation metadata.

If the hard guard passes and the draft is model-generated,
`SemanticRelevanceVerifier` performs one compact authority-free relevance check.
Its input contains only the original request, an allowlisted semantic-plan
summary, and a byte-bounded draft. The result is an `aligned`/`not_aligned`
decision plus a stable reason code. It cannot call tools, claim external
evidence, retry, or store hidden reasoning. Deterministic responses skip this
model verifier.

When postconditions are not satisfied and the response was model-generated,
`SemanticResponseRepairer` may make at most one bounded repair attempt. The
repair receives only the request, bounded violation/relevance information, and
required grounded facts. A repaired candidate re-enters the same final
verification exactly once with repair disabled. If repair is unavailable, empty,
or fails verification, the safe deterministic replacement remains the result.

`ResponseBudgetPolicy` and the universal sanitizer then enforce the one final
user-visible response boundary without starting another model/tool loop.

## Model usage telemetry

`ModelUsageRecorder` keeps normalized per-request call metadata for planner,
response, relevance, and repair calls. Provider-reported input tokens, reasoning
tokens, visible-output tokens, and total-output tokens remain distinct from the
character-derived `estimated_input_tokens`; unsupported/unknown values stay
`null`, never fabricated as zero. Configured reasoning effort is recorded
separately from actual provider reasoning-token usage.

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
still wires the semantic planner as the primary natural-language path. The
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
