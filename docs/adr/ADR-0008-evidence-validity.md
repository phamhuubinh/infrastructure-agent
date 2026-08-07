# ADR-0008 — Evidence validity and provenance

# Status

Accepted

---

# Context

Infrastructure collection has several materially different outcomes: a
measurement can be observed as zero, a query can successfully return no
objects, a command can fail, a source can be unsupported, a cached observation
can be too old, or sources can disagree. A dict/tuple-only contract collapses
these states and makes it easy to report an unavailable metric as healthy.

Assessment quality depends on knowing which observation is usable and why. The
pipeline also needs a stable way to link a response claim to its source without
passing unbounded raw output or credentials to the model/UI.

---

# Decision

The evidence boundary is explicit and typed.

1. A backend command returns immutable `CommandResult` with status, exit code,
   separate streams, safe target/command metadata, duration, and redacted
   serialization. `SUCCESS` and `EMPTY_SUCCESS` are the only command-success
   states.
2. A Child Tool returns `CapabilityResult`. Only `VALID` and `VALID_EMPTY` are
   valid evidence. `PARTIAL`, collection failure, unsupported environment,
   invalid parameters, and parse failure remain visible but never satisfy a
   required-evidence contract.
3. `EvidencePackage` carries raw data separately from structured status,
   failures, warnings, command results, source metadata, facts, and recovery
   records. Raw serialization is opt-in, bounded, and not a provenance
   replacement.
4. Canonical `Fact` is the unit of deterministic reasoning. It always carries
   subject, metric, explicit unit, value, observed/collected times, source,
   target, validity, freshness, confidence, dimensions, and `Provenance`.
5. Zero is a measurement only for a `VALID` Fact. An empty payload is an
   observation only for `VALID_EMPTY`. Failures must not be represented as
   zero, empty collections, or missing values that look like measurements.
6. Completeness, cache reuse, deterministic responders, and rule evaluation
   require valid, fresh evidence. Stale, contradictory, unsupported,
   schema-invalid, failed, and not-collected Facts are first-class states and
   become explicit uncertainty rather than a negative/healthy conclusion.
7. Reconciliation marks conflicting same-scope Facts as contradictory.
   Findings and model claim validation reference Fact IDs/provenance links,
   rather than inferring trust from display text.

---

# Consequences

## Positive

- Collection failure cannot silently become a healthy measurement.
- Evidence completeness and caching have deterministic, testable semantics.
- Facts/Findings provide bounded, auditable provenance for responses.
- Operators can distinguish environment, transport, parser, and source errors.

## Costs

- Collectors and normalizers must preserve more metadata.
- Existing tuple/dict callers need a time-bounded compatibility adapter.
- An assessment may correctly be less conclusive when evidence is stale or
  unavailable.

## Rejected alternatives

- **Use `None`/empty containers for every absence.** Rejected because it
  confuses an observed empty state with a command/API failure.
- **Let the Assessment Model infer validity from raw output.** Rejected because
  a model cannot reliably distinguish command failure, stale cache, or schema
  drift and must not decide collection policy.
- **Drop failed evidence completely.** Rejected because users/operators need a
  safe explanation of what was not collected and why.

---

# Related records

- Short-form decision: `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-023.
- `ADR-0007-deterministic-pipeline.md` — pipeline boundary.
- `ADR-0009-deterministic-reasoning-v1.md` — how valid Facts become Findings.
- `docs/ai/05_EXECUTION_PIPELINE.md` — runtime contract.
