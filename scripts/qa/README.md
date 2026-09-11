# Orion live QA

`make qa-smoke`, `make qa-full`, and `make qa-stability` are manual-only live commands: they are
not dependencies of tests, lint, acceptance, CI, installation, builds, or Orion startup. They
launch isolated loopback Orion APIs with temporary SQLite databases and exercise the current HTTP
session API. They never use Docker or the legacy `/api/query` endpoint. The runner reads an active
local model profile without modifying it, or uses `ORION_QA_MODEL_BASE_URL`,
`ORION_QA_MODEL_ID`, and optionally `ORION_QA_MODEL_API_KEY`.

`qa-smoke` runs the curated 15-case fast tier selected from the current 88-case canonical corpus.
`qa-full` runs all 88 canonical cases. `qa-stability` is a separate two-case tier, not an extension
of the canonical tier. `--case-id <canonical-case>` runs one case in its selected mode; the runner
has no current historical execution phase or `--historical-suite` option.

The five-suite, 386-turn mapping remains historical documentation only. It records prior source
material and is not a corpus executed by the current runner, so it must not be reported as current
QA coverage or acceptance evidence.

`qa-stability` is a separate opt-in suite for broad prompts whose open-ended model/tool loops have
previously exposed timeout instability. Its `enterprise-readiness` and `weekly-synthesis` prompts
preserve the original text verbatim. The bounded variants in `qa-full` exercise a narrower QA
contract; their completion does not demonstrate that the runtime timeout for the original prompts
has been fixed. Stability cases remain read-only: the same execution guard blocks every mutating
tool before its handler, and forbidden-tool checks also report attempted mutation.

Reports are written under `artifacts/qa/`. Linux, Grafana, and Zabbix cases are explicitly
reported as `SKIP` unless a safe QA capability is configured; they never target production files.
Manual-quality cases, stability cases, and the two corresponding bounded synthesis cases retain a
`stability_diagnostic` transcript in both checkpoint and final reports: assistant text,
tool-call arguments, result data, source references, and errors. Known API/environment secrets
and credential-shaped fields are redacted. Reports are local operational evidence; inspect
them before sharing because infrastructure readings and identities are intentionally retained.
The bounded transcript supplies the full terminal answer/evidence required by the quality
sidecar; the 512-character preview is not review evidence. Missing or truncated diagnostics
remain not assessable.

Runner version 13 captures `runtime_input_diagnostics` using authoritative message-response
identities or exact session-scoped QA SQLite deltas, never public timeline items. Entries preserve
one-based
`send_index`, `session_id`, and `request_id` for each attempted send, across turns and sessions.
Exact-request captures are fetched before the temporary API shuts down, with runtime bounds
and redaction retained. Optional missing, empty, malformed, or mismatched diagnostics are
`capture_status: unavailable` with a deterministic reason; they do not change execution status.

Every send snapshots request IDs before and after exactly one POST, using a fresh read-only
connection to that execution's isolated temporary QA database. This is QA evidence coupling to
the stable `requests(request_id, session_id)` table, not a production store/API change. There
are no migrations/writes, lock waits, POST retries, or waits for request completion.
On success, a valid response ID always wins, even if observation fails or the delta disagrees.
On timeout/HTTP error, only `after_ids - before_ids` containing exactly one same-session ID may
bind the observation. The original timeout/error still propagates. This association relies on
the runner's serial sends and exclusive ownership of the temporary session/database; it never
selects a latest row, timestamp, another session, or a prior turn's ID.
`request_identity_source` is `message_response`, `qa_database_delta`, or `unavailable`.
Zero/ambiguous deltas or failed reads retain `request_id: null` with a fixed, bounded
`request_identity_reason`; raw SQLite errors, database paths and content are not reported.
A request not yet committed when the after-snapshot runs remains unavailable; the observer
does not poll for it. Recovered timeout IDs allow exact-request diagnostics before shutdown,
but records must still all match that ID and may be unavailable or incomplete.

Legacy reports without these entries have no request capture evidence; this change does not
repair them. Manifest and sidecar schema versions are
unchanged; the runner version records the additive evidence change.

Each execution exclusively reserves its report directory before writing any checkpoint or
final artifacts. An existing run directory causes failure without retry, reuse, or modification;
missing parent directories are created as needed.

Each new manifest is versioned and checkpoints its execution provenance before the first case:
Git HEAD/tree and dirty state, hashes of allowlisted QA/runtime source files, canonical and
stability corpus hashes, selected case phase/ID plus prompt/assertion hashes, and effective model,
endpoint, timeout, and temperature settings. Hashes identify input differences but are not a
reproducible snapshot of a dirty tree; raw diffs and credentials are never stored. Compare reports
only when their source, corpus, selected case phase/prompt/assertion, and effective settings match.
A canonical case and a stability case with the same ID are not directly comparable. Older manifests
without these fields remain readable but have insufficient provenance for direct comparison.

`PASS` means the automatic case assertions passed. `FAIL` means an automatic assertion or runtime
request failed. `SKIP` means a required optional safe capability was not configured. `MANUAL_REVIEW`
means the deterministic checks completed but answer quality still requires human review; it is never
an automatic PASS.

A manual-quality row is reviewable only when its execution status is `MANUAL_REVIEW`
and its terminal evidence is complete and untruncated. `FAIL`, `SKIP`, or any other outcome
is `not_assessable`, even if an earlier turn has a terminal answer. Reviewer sidecars,
including attempted accepted or duplicate verdicts, cannot override this completion boundary.
Successful multi-turn review subjects hash the last terminal answer and the full captured
transcript. Legacy rows without a `manual_quality` marker remain `unknown`, never implicitly
accepted; existing sidecars are validated against the execution boundary and exact subject.

Each text/payload includes its redacted character count and an explicit `*_truncated` flag.
Assistant text is capped at 65,536 characters, each structured value at 131,072 serialized
characters, and capture at 256 timeline entries. An oversized structured value becomes a JSON
excerpt string with its truncation flag set. Hidden-reasoning-tagged assistant text is omitted
and marked `hidden_reasoning_omitted`. `terminal_response` distinguishes persisted terminal
answers from intermediate tool-call turns. The short `manual_review_answer` preview remains
512 characters and now explicitly marks truncation. No terminal answer exists to review when
the request times out before one is persisted. `MANUAL_REVIEW` is never an automatic PASS.

See [the synthesis investigation](STABILITY_INVESTIGATION.md) for report locations,
source-backed quality reviews and unresolved runtime evidence after PR #121.

## Post-hardening live acceptance

Implementation issues #124–#136 are intentionally validated offline and must not use live QA
as their completion gate. After those hardening dependencies have a clear outcome, issue
[#137](https://github.com/phamhuubinh/infrastructure-agent/issues/137) runs a separate frozen
live acceptance batch.

See [LIVE_ACCEPTANCE.md](LIVE_ACCEPTANCE.md) for the protocol. The candidate commit/tree,
corpus, model/config, timeout, fixture/data policy, repetition counts and review rubric are
declared before the first live call and remain fixed for the batch. Results are reported
separately for deterministic correctness, completion reliability and grounding/answer
quality; CI or offline PASS does not substitute for those live verdicts.
