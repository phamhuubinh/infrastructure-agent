# Evidence and Results

## Observation contract

Normalized observations preserve capability/action identity, status, target/source, timestamp, static/dynamic classification, bounded facts/result, provenance, safe warnings/errors, and recoverability hints.

## Attempted/dispatched/successful are different

Keep distinct:

- proposed action;
- validated action;
- dispatched execution;
- completed execution;
- observation status;
- successful usable evidence.

`budget.actions_used` can prove budget consumption/dispatch; it does **not** prove successful evidence.

## Validity

Failure is not CPU `0%`; failed query is not a valid empty metric set; missing data is not zero; stale data is not fresh.

## Final-answer checks

Before delivery, deterministic checks enforce objective facts without semantic re-routing:

- no claim that a tool ran/succeeded without supporting observation;
- claimed target/source matches observations;
- failed/blocked/unavailable/stale observation is not described as fresh success;
- deterministic calculator/result claims match structured result;
- required provenance/freshness metadata is present;
- protected-information/redaction and response/trace bounds hold.

If necessary, evolve the model contract to include structured claim/evidence references rather than attempting a language-specific post-router.

Exact deterministic work is prompted toward an available deterministic
capability through disclosed group metadata. Ordinary evidence-free FINAL
answers remain valid; however, a structured deterministic FINAL claim must
reference matching successful evidence. Local CLI status/verbose output may
project only the correlated decision/discovery/action/evidence lifecycle and
aggregate trace counts—never prompts, answer reasoning, or raw evidence.

When a parsed FINAL fails only this objective completion validation, the
harness emits a redacted completion-rejection event and returns bounded
machine-readable feedback to the model. It may then discover, act, clarify,
refuse, or produce a corrected FINAL. Repeated equivalent rejected claims stop
as no-progress; a completion obligation remains turn-local until its required
successful evidence or corrected evidence-backed claim exists, so a claimless
retry cannot erase it. Malformed protocol output remains subject to the normal
protocol failure path.
