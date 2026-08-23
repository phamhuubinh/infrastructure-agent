# Evidence and Results

## Goal

Every tool call should return a result the model can reason about without
receiving an uncontrolled dump of implementation internals.

## Observation contract

A normalized observation should include, when applicable:

- action/capability identity;
- success, partial, unavailable, rejected, or failed status;
- target identity;
- source/connection identity;
- observation timestamp;
- static/dynamic classification;
- compact facts or result payload;
- provenance references;
- safe warnings/errors;
- recoverability hints;
- bounded metadata useful for the next decision.

Raw command output or huge API payloads should remain behind the evidence layer
unless a specific capability intentionally exposes bounded raw content.

## Validity

Failures must not be converted into healthy-looking values.

Examples:

- a command failure is not CPU `0%`;
- a failed query is not an empty metric set;
- missing data is not a valid zero;
- a stale observation is not a newly collected observation.

## Provenance

Evidence should retain enough provenance to answer:

- where did this come from?
- which target/source did it describe?
- when was it observed?
- which capability produced it?
- was collection successful?

The user-facing answer may show concise citations/source labels when useful,
while debug traces can retain safe structured provenance.

## Conflicting evidence

The evidence layer should not hide disagreement between sources. If Linux,
Grafana, and Zabbix disagree, preserve the observations and let the model assess
why they differ.

Deterministic normalization may identify exact contradictions or incompatible
scopes, but it should not replace the model's higher-level assessment with
language-specific rules.

## Dynamic evidence

Dynamic observations remain stored as observations with time, not as timeless
truth. A later request can reuse them as historical context or collect again.

## Final-answer checks

The delivery boundary should verify objective execution facts such as:

- the model must not claim a tool ran when it did not;
- a claimed target/source should match validated observations;
- deterministic calculator values must match the result;
- secret/redaction policy must hold;
- response size and public trace bounds must hold.

The completion layer should not re-interpret the user's natural language to
choose tools or sources after the model has already reasoned about the request.
