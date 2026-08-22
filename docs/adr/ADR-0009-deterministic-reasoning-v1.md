# ADR-0009 — Deterministic reasoning v1

# Status

Accepted as historical v1 context; primary reason/action/recovery selection is
superseded by Agent v2. Deterministic Facts/findings/rules, evidence validity,
reviewed Child Tool logic, deterministic budgets, and safety remain current.

---

# Context

After evidence is collected, Orion needs repeatable health signals and a
bounded way to pursue missing evidence. Delegating execution recovery,
threshold decisions, or evidence expansion to free-form model output would
make command paths, stop conditions, and safety posture non-reproducible.
Agent v2 is compatible with the still-current deterministic boundaries: its
controller may select the next validated approved action after an observation,
but it does not replace deterministic evidence, execution, safety, or
completion controls.

---

# Decision

Deterministic reasoning v1 is a limited code path over canonical Facts:

1. Reviewed, versioned atomic threshold rules derive atomic Findings from
   valid, fresh Fact metrics.
2. Reviewed composite rules evaluate explicit `WeightedCondition` values. They
   retain coverage, observable/missing weight, support/contradiction, and
   insufficient-evidence outcomes; missing observations are not silently
   reweighted unless the reviewed rule explicitly requests it.
3. Findings contain deterministic decisions, rule/version identifiers,
   confidence, supporting/contradicting Fact IDs, missing metrics, and
   provenance links. `HealthAggregator` combines this data without inventing
   a conclusion for unavailable evidence.
4. Recovery can invoke only alternatives declared in capability metadata for a
   declared recoverable error. It is capped at depth two, shares the
   investigation budget, stops on transport failure, and records attempts.
5. A weighted missing-evidence selector can make at most the bounded expansion
   allowed by `ExecutionBudget`; it cannot call arbitrary new capabilities.
6. **Superseded for primary reason/action/recovery selection:** v1 confined the
   model to high-level semantic classification and explanation. The current
   Agent v2 controller may select the next validated approved action after a
   compact observation. It still does not generate commands, authorize an
   unvalidated capability/target, select arbitrary recovery, revise thresholds,
   expand the execution budget, or self-train rules from a conversation.
7. Rule configuration is schema-validated, versioned, owned, sourced to test
   cases, and approved before production loading. A production engine fails
   loudly rather than silently falling back to unreviewed rules.

---

# Consequences

## Positive

- The same validated plan/evidence/rule version yields the same deterministic
  reasoning outcome.
- Unknown, stale, failed, and contradictory evidence stays visible.
- Recovery and expansion have predictable cost, stop conditions, and traces.
- Rule changes receive normal review and can be tested for precision/recall.

## Costs

- New operational conditions require explicit Facts and a reviewed rule, not a
  prompt edit.
- The v2 controller can pursue a bounded hypothesis only through validated
  approved actions; it cannot open arbitrary tool/recovery branches.
- Some requests end with `INSUFFICIENT_EVIDENCE`, which is safer than a false
  deterministic conclusion.

## Rejected alternatives

- **LLM-authorized tool/recovery execution.** Rejected: model output may
  describe semantic intent, but direct control of commands, recovery choices,
  or stop conditions violates the execution boundary.
- **Self-learning rules from live conversations.** Rejected: it removes the
  owner/version/review controls required for operational thresholds.
- **A broad expert-system platform.** Rejected: v1 needs only structured
  Facts, atomic/composite rules, bounded recovery, and weighted selection.
- **Treat missing conditions as false.** Rejected: absence is not contradictory
  evidence and would systematically under-report uncertainty.

---

# Related records

- Short-form decision: `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-021.
- `ADR-0008-evidence-validity.md` — Fact validity/freshness/provenance.
- `ADR-0002-llm-assessment-only.md` — model authority boundary.
- `docs/ai/05_EXECUTION_PIPELINE.md` — runtime flow and bounded recovery.
