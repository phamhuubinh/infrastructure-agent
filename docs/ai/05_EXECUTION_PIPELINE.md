# 05 - Execution Pipeline

This document describes the implemented deterministic investigation pipeline.
`08_PROJECT_STATE.md` remains the source of truth for delivery status; this
document defines the execution contract.

## Boundary

Orion follows **Code investigates. AI explains.** Deterministic code resolves
the request, validates parameters, selects declared capabilities, runs only
reviewed collection strategies, normalizes evidence, and evaluates rules. The
Assessment Model receives an `AssessmentRequest` after that work; it never
chooses a target, capability, command, fallback, or recovery path.

```text
User request + session context
        |
        v
RequestFrame -> routing / clarification -> target / parameters
        |
        v
Evidence requirements -> capability plan -> execution DAG
        |
        v
KnowledgeTool -> Child Tool -> CommandResult -> CapabilityResult
        |
        v
EvidencePackage (raw + failures + canonical Facts + provenance)
        |
        v
Completeness / reconciliation -> atomic & composite Findings
        |
        +--> DeterministicResponder for bounded fact/list/table responses
        |
        +--> AssessmentRequest -> LLM explanation -> output guards
        |
        v
Final response + ExecutionTrace
```

Every investigation has one `ExecutionTrace`; it records stage outcomes,
resolved target and parameters, planned and collected evidence, strategy, LLM
usage reason, and a safe failure stage/reason when execution cannot continue.

## Stages

1. **Request and routing** — `Normalizer`, session-context resolver, and
   `IntentResolver` create/complete an immutable `RequestFrame`. Ambiguous,
   unsafe, unsupported, or unknown-target requests return a deterministic
   clarification or refusal. They do not fall back to model planning.
2. **Evidence and capability planning** — `EvidencePlanner`,
   `CapabilityPlanner`, `CapabilityResolver`, and `ParameterBinder` express
   requirements as canonical metric/target/parameter contracts and resolve
   them to registered Child Tool capabilities. Required parameters are
   validated before dispatch.
3. **Execution** — `ExecutionPlanner` and `ExecutionGraphBuilder` create a
   dependency DAG. `ExecutionRuntime` dispatches each node only through
   `KnowledgeTool`, runs independent nodes in parallel, applies the shared
   budget, and records safe runtime metrics.
4. **Merge and validity** — `EvidenceMerge` retains raw payloads for audit,
   carries structured failures, normalizes valid output into Facts, reconciles
   conflicts, and runs `EvidenceCompleteness`. A cache may reuse only fresh
   `VALID`/`VALID_EMPTY` evidence.
5. **Deterministic reasoning** — atomic thresholds and reviewed composite
   rules turn valid, fresh Facts into source-linked Findings. Missing, stale,
   contradictory, unsupported, and failed observations are represented as
   unknown/insufficient evidence, never coerced to a healthy value.
6. **Response** — `DeterministicResponder` answers simple supported requests
   directly. Otherwise `AssessmentAdapter` builds an `AssessmentRequest` for
   the model. Output guards keep claims grounded and preserve the read-only
   boundary.

## Result contracts and failure semantics

`CommandResult` is the immutable result of one backend command. It contains
`status`, `exit_code`, separate `stdout`/`stderr`, `error_type`, safe target
metadata, duration, and a redacted serialization. `success` is true only for
`SUCCESS` and `EMPTY_SUCCESS`; an empty successful command is distinct from a
collection error.

`CapabilityResult` is the Child Tool outcome. `VALID` and `VALID_EMPTY` are
the only successful statuses. `PARTIAL`, `COLLECTION_FAILED`, `UNSUPPORTED`,
`INVALID_PARAMETERS`, and `PARSE_FAILED` retain their data/diagnostics where
safe but cannot satisfy a required-evidence contract. They carry a stable
`CapabilityError` code/category/recoverability value, not policy inferred from
an error message.

`EvidencePackage` preserves the capability result, raw data (opt-in and size
bounded in serialization), warnings, collection failures, source/parameters,
command provenance, Facts, and recovery metadata. A package is valid for a
requirement only when it is fresh and has status `VALID` or `VALID_EMPTY`.

No stage may turn a failure into `0`, `[]`, `{}`, or `None` and present it as a
measurement. `VALID_EMPTY` means a collector successfully observed an empty
domain; it does not mean an unsuccessful command found nothing.

## Facts, provenance, and Findings

A canonical `Fact` is immutable and identifies a subject, dotted metric,
value, explicit unit, observed/collected time, source, target, validity,
freshness, confidence, dimensions, and `Provenance`. Only a valid zero is a
numeric zero. A stale, contradictory, schema-invalid, unsupported, failed, or
not-collected Fact is kept distinct so that `EvidenceCompleteness` and rules
can report the actual limitation.

`FactReconciler` marks incompatible same-scope observations as contradictory.
`Finding` records the deterministic rule decision, score/coverage/confidence,
supporting and contradicting Fact IDs, missing metrics, rule version, and
claim-source links. This makes both deterministic and model-generated claims
auditable without exposing credentials or unbounded raw output.

## Bounded recovery and expansion

Recovery is capability metadata, not a model decision. `CapabilityRecovery`
may try declared alternatives only for declared recoverable errors, observes a
maximum depth of two, stops on target-wide transport failure, and records every
attempt. It cannot invent a shell command or retry a non-recoverable error.

When evidence remains incomplete, `EvidenceExpander` can select one weighted
missing-evidence round under the common `ExecutionBudget`. Stop conditions
include sufficient evidence, transport failure, exhausted duration/tool-call
budget, and no eligible candidate. The Assessment Model cannot request another
round.

## Compatibility and rollout

Legacy tuple unpacking of `CommandResult` and raw Child Tool payloads are
temporary adapters. They continue to work during the migration window but emit
`DeprecationWarning` for direct callers; new code must use named
`CommandResult` fields and return `CapabilityResult`. See
`docs/migrations/deterministic_reasoning_v1.md` for the caller matrix and
removal criteria.

`config/feature_flags.yaml` and `ORION_FEATURE_*` overrides can roll back
structured command provenance, canonical Fact exposure, composite findings,
and claim grounding independently without changing the external response
schema. Flags are migration controls, not permanent product configuration.

## Related documents

- `06_TOOL_AND_CAPABILITY_DESIGN.md` — Child Tool ownership and contracts.
- `docs/adr/ADR-0008-evidence-validity.md` — evidence validity decision.
- `docs/adr/ADR-0009-deterministic-reasoning-v1.md` — deterministic reasoning
  decision.
- `docs/troubleshooting.md` — operator diagnosis for collection failures.
