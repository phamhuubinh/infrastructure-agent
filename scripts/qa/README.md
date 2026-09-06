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
Stability cases and the two corresponding bounded synthesis cases retain a
`stability_diagnostic` transcript in both checkpoint and final reports: assistant text,
tool-call arguments, result data, source references, and errors. Known API/environment secrets
and credential-shaped fields are redacted. Reports are local operational evidence; inspect
them before sharing because infrastructure readings and identities are intentionally retained.

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
