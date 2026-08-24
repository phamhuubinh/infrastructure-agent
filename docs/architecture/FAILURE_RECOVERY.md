# Failure and Recovery

The model receives safe structured failure feedback and chooses the next semantic step. The harness does not silently switch strategy using a hard-coded semantic fallback.

Deterministic runtime owns stage legality, retry/deadline/resource bounds, no-progress, permission, safety, and typed errors.

## No progress

Count repeated identical actions/results, repeated forbidden-stage decisions, repeated undisclosed capability proposals, repeated invalid discovery, and feedback cycles with no new evidence/disclosure/authority state.

Terminate such cycles explicitly before they merely exhaust generic model-call budget where feasible. Raising the model-call limit is not a fix.

## Persistence failures

Corrupt metadata is preserved/quarantined and mutations fail closed until recovery. Multi-store mutation failures leave consistent or explicitly recoverable state, not silent partial success.
