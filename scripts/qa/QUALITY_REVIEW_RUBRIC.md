# QA answer-quality review rubric

This is a human-review rubric for the offline `quality-verdicts.jsonl` sidecar. It
does not judge answers automatically, and a deterministic QA `PASS` or
`MANUAL_REVIEW` is not an accepted quality verdict.

Review the exact terminal answer and the evidence bound by the hashes emitted by:

```bash
python scripts/qa/quality_verdicts.py inspect scripts/qa/reports/<run-id>
```

Only enter `accepted`, `rejected`, or `not_assessable` after checking the following
counterexamples from the rejected #122 synthesis answers. The examples are
synthetic; they intentionally contain no infrastructure identities.

- Do not say a service is `active/running` when its source says `inactive/dead` or
  `not-found`.
- “Recent” must refer to an event's occurrence time, not its retrieval time. An
  April event is not recent in a September weekly report.
- A one-event query without explicit weekly bounds cannot establish that no event
  happened during that week.
- A point-in-time CPU/memory/disk snapshot cannot establish capacity, sustained
  workload readiness, or swap-in/swap-out activity. In particular, `SwapFree` and
  `SwapCached` do not prove swap activity or its absence.

Mark an answer `not_assessable` when the artifact has no terminal answer, omits
required evidence, or explicitly marks the answer/evidence as truncated. The gate
never upgrades such an artifact to `accepted`.

## Sidecar record

Write one JSON object per line in `quality-verdicts.jsonl`. Copy the run identity,
phase, case ID, and hashes exactly from `inspect`; add the human decision fields.

```json
{
  "schema_version": 1,
  "run_id": "20260906T000000Z-example",
  "manifest_sha256": "...",
  "execution_fingerprint": "...",
  "phase": "canonical",
  "case_id": "synthetic-synthesis",
  "answer_sha256": "...",
  "evidence_sha256": "...",
  "verdict": "rejected",
  "rationale": "The answer claims a bounded weekly absence from an unbounded query.",
  "reviewer": "reviewer-label",
  "reviewed_at": "2026-09-06T00:00:00Z"
}
```

The offline release gate is explicit about skip coverage; it does not treat `SKIP`
as sufficient evidence by default:

```bash
python scripts/qa/quality_verdicts.py gate scripts/qa/reports/<run-id> --skip-policy forbid
```

Use `--skip-policy allow-with-rationale --skip-rationale '...'` only when a
documented coverage exception is actually approved. The command returns nonzero for
automatic `FAIL`, pending/rejected/not-assessable required review, invalid or
duplicate sidecars, or a coverage-policy violation. It reads artifacts only; an
optional `--output` writes a separate overlay report and never rewrites
`cases.jsonl` or the execution manifest.
