# Orion live QA

`make qa-smoke`, `make qa-full`, and `make qa-stability` are manual-only live commands: they are
not dependencies of tests, lint, acceptance, CI, installation, builds, or Orion startup. They
launch isolated loopback Orion APIs with temporary SQLite databases and exercise the current HTTP
session API. They never use Docker or the legacy `/api/query` endpoint. The runner reads an active
local model profile without modifying it, or uses `ORION_QA_MODEL_BASE_URL`,
`ORION_QA_MODEL_ID`, and optionally `ORION_QA_MODEL_API_KEY`.

`qa-smoke` is the curated 15-case fast suite. `qa-full` runs the current 25 structured acceptance
cases and the five-suite, 386-turn historical behavioral corpus. Historical prompts are immutable
test data: they keep source order and session continuity, but only require request success, a safe
non-empty final response, and no configured-credential leakage. They do not assert legacy routing
or tool choices.

The historical phase starts a separate API process with an explicitly empty infrastructure
configuration. This prevents fallback SSH and credential discovery and ensures historical mutation
requests cannot target configured infrastructure. `--case-id <structured-case>` runs only that
structured case; `--historical-suite <suite-id>` (with `--mode full`) runs only one historical
suite for manual debugging.

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
