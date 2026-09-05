# Synthesis stability investigation — 2026-09-05

This follow-up starts at `3c24937` (main after PR #121). It is a partial mitigation
and evidence/reporting change, **not a demonstrated runtime-timeout or answer-quality fix**.
The original stability prompts, mutation execution guard, assertions, and 90-second QA
timeout remain unchanged. No total tool-call quota has been introduced.

## Evidence captured before runtime changes

Report `artifacts/qa/20260903T134156Z-c430be1a/cases.jsonl` was collected after adding
diagnostics and before changing runtime guidance or infrastructure results. Both original
cases completed as `MANUAL_REVIEW`, not PASS. Their full assistant texts (2,144 and 1,456
characters) and corresponding tool data/sources have false truncation flags. These local
reports deliberately remain untracked because they contain infrastructure identities and
readings even after credential redaction. The excerpts below are intentionally incomplete;
the report contains the complete review material.

### Separate quality review: both rejected

- Enterprise: only a Linux snapshot was successfully read. The answer inferred low CPU
  utilization, sufficient basic-workload capacity, no imminent disk exhaustion, installed
  critical packages, no active monitoring alerts, and a 7/10 readiness score. Neither
  workload requirements/history nor package/monitoring evidence supported those findings.
  Calling them assumptions did not make the findings sound.
- Weekly: the service source says `not-found/inactive/dead`, but the answer says
  `active/running`. Actual problem triggers concern link-down, DHCP and WAN packet loss,
  not the claimed high CPU/disk I/O. A 404 for an invented default dashboard does not prove
  a required dashboard is missing. The event query had no weekly bounds and returned old
  April/May events, despite September retrieval. Omitted model-context records are gaps,
  not permission to reconstruct details. This is not a valid weekly synthesis.

Source correlation examples in that report: service
`84627387-c81e-512e-8eb5-3f213208a2de`, triggers
`99a62162-8508-5a21-b8f9-616766c24b89`, events
`e9b5f495-e1aa-5cd3-bfe0-2fabc6cb9182`. Retrieval timestamps are not event occurrence times.

## Runtime evidence and limits of the diagnosis

- `20260903T132850Z-413de3a0`: both original cases timed out. The later baseline above
  completed without a runtime fix: this already establishes intermittency.
- `20260905T101631Z-a8ece853`: enterprise retried invalid target identities such as
  `linux: monitor` and `linux:monitor`. The old context displayed family and identity as
  `linux: monitor`. Weekly selected an unrelated 2023 interval without an application clock
  in its infrastructure context, then performed broad reads without a terminal answer.
- `20260905T102121Z-3d374472`: after explicit target JSON and current UTC context, weekly
  used the correct target and August 29–September 5, 2026 interval, but still timed out.
  Successful source retrievals were at 10:22:20 (inspect), 10:22:42 (events), and 10:22:59
  (Grafana), before the run ended at 10:23:20. Sequential model/tool rounds consumed much
  of the request window. The trace does not establish what the provider was doing while
  waiting for the final response. Enterprise returned only a plan/offer, also rejected.
- `20260905T102447Z-96e08501`: with proportionate-read/batching guidance, enterprise
  completed as MANUAL_REVIEW; weekly timed out with only the user timeline entry and no
  persisted assistant/tool events. This instance cannot be described as a post-data loop.

Observed contributors are ambiguous target context, missing application-time context,
schema/recovery rounds, unnecessary exploration and sequential model round trips. Neither
a single universal root cause nor elimination of the provider/model completion problem has
been proven. In particular, report capture cannot recover a final answer that was never
persisted. No hidden reasoning is collected.

## Changes under test

- Report full redacted assistant text and corresponding arguments/results/sources for both
  stability and bounded synthesis cases, including timeout checkpoints. Explicit caps and
  omission flags distinguish incomplete capture from absent terminal output.
- Expose exact target identities and current UTC in infrastructure context; guide bounded,
  authorized evidence collection, independent-read batching, and explicit unknown identifiers.
- Add point-in-time/missing-section limitations to Linux results and explicit occurrence
  timestamps/query coverage to Zabbix events. Prioritize that metadata during projection.
- Add post-observation grounding/synthesis guidance without disabling further useful tools.
  This is model guidance, not a semantic output validator or completion guarantee.
- Regress missing memory, old April events, projected coverage, exact target/time context,
  continued follow-up tool availability, and report redaction/truncation/checkpoint behavior.

## Verification

`make acceptance`: PASS (323 backend tests, 54 UI tests, packaged UI, architecture/OpenAPI/
operations checks, lint, formatting, type checks and build).
The final repeat also exited 0, with an intermittent worker-cleanup warning
(`Event loop is closed` in `test_package_convergence_and_zabbix_acknowledgement_dispatch_once`).
That lifecycle warning is recorded separately; this PR does not claim to fix it.

Latest original stability run: `20260905T102447Z-96e08501`:

| Case | Automatic result | Separate quality review |
| --- | --- | --- |
| enterprise-readiness | MANUAL_REVIEW | Rejected: minimal contention, adequate idle-workload memory, no immediate exhaustion risk remain unsupported. SwapFree is also not exactly SwapTotal, despite the claim of full availability. |
| weekly-synthesis | FAIL: QARequestTimeout | Not assessable: no persisted final answer. |

The enterprise answer and its source are fully captured with false truncation flags. It now
acknowledges missing monitoring/baselines and timestamps its snapshot, but those improvements
do not cancel the unsupported conclusions. Acceptance regressions verify contracts/context;
they do not prove that a live model obeys grounding guidance. This PR must not be presented
as closing either unresolved runtime stability or answer-quality issue.

Related bounded cases, run separately on the same code after acceptance:

| Case / report | Automatic result | Separate quality review |
| --- | --- | --- |
| enterprise-readiness / `20260905T143458Z-4a6b0697` | MANUAL_REVIEW | Rejected: low load is called minimal contention; `SwapCached=84kB` is used to claim no swap activity; no imminent disk pressure is unsupported. Stated limitations contradict these claims. |
| weekly-synthesis / `20260905T143548Z-d5140ed9` | MANUAL_REVIEW | Rejected: calls the April 13 event recent despite also noting it is outside August 29–September 5. Infers no events occurred that week from a one-event, unbounded query (`query_window_explicit=false`). Also reports swap free greater than its rounded total. |

Both full bounded answers and corresponding source data have false truncation flags. The
weekly answer correctly limits Linux capacity conclusions and recognizes the old timestamp,
but still draws an unsupported absence-of-events conclusion. These results demonstrate why
MANUAL_REVIEW must remain distinct from PASS, and why prompt/metadata improvements alone
are insufficient to close this issue. The follow-up is draft/not ready for merge as a fix.
