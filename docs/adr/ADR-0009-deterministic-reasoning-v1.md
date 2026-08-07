# ADR-0009 — Deterministic reasoning v1

# Status

Accepted

---

# Context

After evidence is collected, Orion needs repeatable health signals and a
bounded way to pursue missing evidence. Delegating those decisions to an LLM
would make the selected capability, command path, stop condition, and safety
posture non-deterministic. Conversely, a large self-learning expert system is
out of scope and would obscure review of production rules.

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
6. The Assessment Model explains the resulting facts/findings and uncertainty.
   It does not plan, select capabilities, select a recovery, generate commands,
   revise thresholds, or self-train rules from a conversation.
7. Rule configuration is schema-validated, versioned, owned, sourced to test
   cases, and approved before production loading. A production engine fails
   loudly rather than silently falling back to unreviewed rules.

---

# Consequences

## Positive

- The same request/evidence/rule version yields the same reasoning outcome.
- Unknown, stale, failed, and contradictory evidence stays visible.
- Recovery and expansion have predictable cost, stop conditions, and traces.
- Rule changes receive normal review and can be tested for precision/recall.

## Costs

- New conditions require explicit Facts and a reviewed rule, not a prompt edit.
- The model cannot chase an ad-hoc hypothesis mid-assessment.
- Some requests end with `INSUFFICIENT_EVIDENCE`, which is safer than a false
  deterministic conclusion.

## Rejected alternatives

- **LLM-driven tool/recovery planning.** Rejected: it violates the execution
  boundary and produces non-reproducible command/capability choices.
- **Self-learning rules from live conversations.** Rejected: it removes the
  owner/version/review controls required for operational thresholds.
- **A broad expert-system platform.** Rejected: v1 needs only structured
  Facts, atomic/composite rules, bounded recovery, and weighted selection.
- **Treat missing conditions as false.** Rejected: absence is not contradictory
  evidence and would systematically under-report uncertainty.

---

# Related records

- Short-form decision: `docs/ai/09_ARCHITECTURE_DECISIONS.md` AD-024.
- `ADR-0008-evidence-validity.md` — Fact validity/freshness/provenance.
- `ADR-0002-llm-assessment-only.md` — LLM boundary.
- `docs/ai/05_EXECUTION_PIPELINE.md` — runtime flow and bounded recovery.
