# Frozen post-hardening live acceptance

This procedure is the live acceptance gate tracked by
[issue #137](https://github.com/phamhuubinh/infrastructure-agent/issues/137).
It runs **after** the offline hardening program in #124–#136. It is not a CI job,
not an implementation test, and not permission for those issues to run live model or
infrastructure QA while changing code.

## Why this gate exists

Offline tests can prove runtime, evidence, context, dispatch and review contracts. They
cannot prove that the selected live model/provider path completes reliably or that final
answers stay grounded in the evidence the model actually received.

The acceptance batch therefore freezes its inputs before the first live call and reports
three separate outcomes:

1. deterministic correctness / execution;
2. completion reliability;
3. grounding / answer quality.

A green offline suite or CI check cannot substitute for any of these live verdicts.

## Freeze before the first run

Create and retain a versioned acceptance declaration containing at least:

- clean exact commit SHA and Git tree;
- execution/manifest schema version and execution fingerprint;
- canonical and stability corpus hashes;
- selected case IDs, phases/tiers and prompt/assertion hashes;
- original stability prompt hashes;
- model ID and sanitized endpoint identity;
- provider/stream timeout and effective QA request timeout;
- configured sampling values, with unknown provider defaults left as unknown;
- timezone/application-clock policy;
- infrastructure fixture/data identity or snapshot/version policy sufficient for
  comparability;
- exact run order and repetition counts;
- expected intentional-SKIP/coverage policy;
- quality-review rubric/version and reviewer-label policy;
- predefined environment-invalid/not-assessable rules.

Do not revise this declaration after observing the first live result.

## Default batch

Unless the owner changes the plan **before** the first live call and records the reason in
the declaration, use:

- three complete `qa-full` runs on the same frozen inputs;
- five isolated repetitions of the original `enterprise-readiness` stability case;
- five isolated repetitions of the original `weekly-synthesis` stability case.

Bounded synthesis variants remain separate evidence and do not replace the original
stability prompts. Do not enable live mutation merely to improve coverage. Expected
read-only-policy or safe-fixture skips must be declared before the batch and reported as
coverage not validated live, not as PASS.

## Batch invariants

During one batch, do not change code, corpus, prompt, assertion, tier, `manual_quality`,
timeout, sampling, model, endpoint, fixture/data policy or production configuration. Do not
hotfix after a failure and keep counting later runs under the same batch identity.

A material input change starts a new batch. Dirty or insufficient-provenance runs are
incomparable. External/provider/infrastructure incidents may only be excluded according to
the environment-invalid policy declared before the batch; the original artifacts remain
part of the audit record.

Never rewrite source artifacts or remove a failure from the denominator because a later
run passes.

## Quality review

Use the structured review sidecar introduced by #126. Keep automatic execution status and
quality status separate.

Every quality-required `MANUAL_REVIEW` result in the canonical full runs and every
terminal original-stability answer requires a matching review verdict. Rejected, pending,
not-assessable, stale/mismatched review data or a missing terminal answer is not quality
accepted.

Review against the evidence the model actually received when model-input capture is
available. In particular, reject conclusions that:

- contradict a service/host/trigger state in the source;
- call an old event recent without a valid time window;
- infer absence from an unbounded or incomplete limited query;
- infer capacity or swap activity from a point-in-time snapshot without supporting data;
- treat a visible source reference as proof that omitted evidence detail was visible.

Do not use an LLM judge as the default reviewer for this gate.

## Verdicts

### A. Deterministic correctness / execution

PASS requires all three canonical full runs to have no automatic FAIL, no unexpected SKIP,
comparable provenance, and no diagnosed runtime-invariant violation. Expected intentional
SKIP remains an explicit coverage limitation.

### B. Completion reliability

PASS requires each original stability case to produce a valid terminal completion in all
five repetitions on the frozen batch. Timeout, provider failure and deterministic incomplete
fallback remain non-pass completion outcomes; they must not be relabeled as semantic PASS.

### C. Grounding / answer quality

PASS requires every required quality review to be accepted, with no contradictory or
unsupported conclusion relative to evidence and declared coverage/limitations.

The overall post-hardening live acceptance is PASS only when A, B and C all pass on a
comparable frozen batch.

## Failure handling

Do not repair the candidate inside the batch. Preserve the batch artifacts, execution
fingerprints and reviews, classify the failure, then make any code/config change through a
separate issue/PR. A changed candidate starts a new acceptance batch from the beginning.

The final report must state the exact model/provider/data path tested. Passing this gate is
not evidence that Orion is stable on every model or provider.
