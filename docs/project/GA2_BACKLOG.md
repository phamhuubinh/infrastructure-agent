# Orion — GA2 Backlog (Single Source of Truth)

> **Status:** ACTIVE
> **Snapshot audited:** `orion-f88941d5629c-source.tar.gz`
> **Engineering baseline:** `1918 passed`, Ruff clean (maintainer run)
> **Rule:** this is the only active GA2 backlog. Legacy backlog/task-packet files are history in Git and must not be used as current state.

## 1. Operating rules

1. Work one backlog item at a time.
2. Do not create a new backlog item if the issue fits an existing item below; extend that item's acceptance criteria instead.
3. A helper/unit test is not enough when the contract is runtime behavior. For runtime items, at least one test must exercise the real `DeterministicAgent`/tool path.
4. Never mark an item DONE from test count alone. DONE requires the behavior and negative/fail-closed cases listed for that item.
5. Preserve these invariants while editing:
   - unresolved explicit target => zero environment execution; never localhost fallback;
   - hard source restriction never silently becomes `ANY`;
   - hidden reasoning/system prompts/credentials stay sanitized or refused;
   - SSRF/private/loopback/link-local/DNS-rebinding/redirect protections stay fail-closed;
   - fetch success != extracted content != relevant evidence != sufficient evidence;
   - missing evidence => UNKNOWN/unavailable, never model-memory certainty;
   - Orion remains read-only; generated mutating commands are content, not execution receipts;
   - full GA2 runtime acceptance set remains exactly 386 cases.
6. For implementation work, run targeted tests first. Before DONE: relevant targeted tests, full `pytest`, Ruff, and `git diff --check` must pass.
7. Final 386 runtime acceptance is a maintainer release gate, not something an implementation task can self-declare.

## 2. What is already stable enough to freeze

Do not reopen these as separate backlog items unless a regression test fails:

- unified QA runner/report/artifact plumbing;
- output sanitization and hidden-reasoning/secret boundary;
- unknown-target fail-closed behavior;
- hard source-constraint preservation;
- correction/session target semantics already covered by regression tests;
- EXPLAIN -> INSPECT ordered runtime plan;
- current external requests route to external verification and provider-unavailable paths fail closed;
- provenance receipt/session plumbing already present;
- comparison status helpers (`COMPLETE` / `PARTIAL` / `UNAVAILABLE`) already present;
- deterministic repetition detector exists;
- deterministic config/shell/YAML validators exist;
- effective SSH inspection prefers `sshd -T` and raw fallback does not invent absent directives.

These are **frozen baseline**, not proof that every legacy GA2 task touching them is fully accepted. Remaining integration gaps are consolidated below.

## 3. Active backlog

| Order | ID | Priority | Workstream | Depends on |
|---:|---|---|---|---|
| 1 | GA2-R1 | P0 | External evidence relevance + claim grounding | — |
| 2 | GA2-R2 | P1 | Multi-source comparison + actual provenance closure | R1 only where Internet evidence is involved |
| 3 | GA2-R3 | P1 | SSH `PermitRootLogin` effective-context correctness | — |
| 4 | GA2-R4 | P1 | User-supplied/self-contained reasoning path | — |
| 5 | GA2-R5 | P1 | Generated artifact validation in real runtime | R1 for current-value generation cases |
| 6 | GA2-R6 | P1 | Unified response strategy + final output boundary | R4/R5 behavior must remain distinct |
| 7 | GA2-R7 | P2 | Response/token/latency budgets + metrics | R6 |
| 8 | GA2-R8 | P0 release gate | Fresh 386 runtime acceptance + manual grading | R1-R7 |

---

## GA2-R1 — External evidence relevance + claim grounding

**Why this remains open**

Current external verification distinguishes fetch/extraction states, but the audited code does not yet model **request-relevant evidence** as a first-class state. `outcome.verified` can still be driven by having extracted documents, while the current-claim guard mostly checks whether version/date/price/office-holder text appears somewhere in the fetched corpus. The dedicated external failure matrix also does not itself cover the full legacy failure contract. C07-style routing/fail-closed behavior exists, but a real happy-path test proving a verified value is propagated into the generated artifact is still required.

**Required work**

- Add deterministic request-entity / claim-type extraction sufficient for current version, release date, current price/value, current office holder/identity, and simple factual claims from a supplied URL.
- Select bounded relevant passages and preserve document URL/title/provider association.
- Represent at least: fetch failure, extraction failure/empty/unsupported, extracted-but-no-relevant-evidence, relevant-but-partial/truncated, sufficient relevant evidence.
- `verified`/sufficiency must never become true solely because unrelated page text was extracted.
- Ground concrete current claims only in relevant evidence, not in a citation footer or unrelated corpus occurrence.
- Add a true runtime happy path: verified current value -> generated Dockerfile/config uses that exact verified value.
- Keep unavailable/page-lacks-value cases fail-closed with no fabricated current value.
- Complete deterministic coverage for timeout, DNS failure, HTTP 404/500, unsupported MIME, empty content, oversized/truncated content, invalid/odd encoding, redirect chain, mixed public/private DNS, and public->private redirect. Security cases may remain in Internet-tool tests, but the external-verification outcome must stay insufficient.

**DONE when**

- Agent-level tests prove grounded happy path and page-lacks-value negative path.
- Relevant-evidence state is visible in structured outcome/trace, not only prose.
- All external failure classes remain typed and insufficient.
- Full pytest + Ruff + `git diff --check` pass.

**Primary tests**

- `tests/pipeline/test_external_verification.py`
- `tests/pipeline/test_ga2_external_failure_matrix.py`
- `tests/model/test_claim_validator.py`
- `tests/agent/test_deterministic_agent.py`
- `tests/qa/test_ga2_epics_cd.py`
- `tests/tool/test_internet_tool.py`

---

## GA2-R2 — Multi-source comparison + actual provenance closure

**Why this remains open**

Comparison status helpers and a PARTIAL note exist, and provenance receipts are present. What still needs runtime proof is that every named source is independently executed when available, no unrelated source counts as a substitute, and the previous-answer provenance response names the sources that actually produced evidence.

**Required work**

- For an explicit Grafana + Zabbix comparison, prove both requested sources are planned/executed when capabilities exist.
- Keep source-specific facts/receipts separate through response construction.
- `COMPLETE` only when both requested sides have usable evidence; `PARTIAL` when one side does; `UNAVAILABLE` when neither does.
- PARTIAL/UNAVAILABLE response names the exact missing source(s).
- Previous-answer provenance must prefer actual evidence receipts over requested/allowed constraints.
- Add runtime tests for COMPLETE, PARTIAL, UNAVAILABLE, and a provenance follow-up after each relevant case.

**DONE when**

- Real agent/runtime tests prove execution + per-side provenance; helper-only status tests are not the closure evidence.
- No Linux/SSH/ANY substitution can make a missing Grafana/Zabbix side appear complete.

---

## GA2-R3 — SSH `PermitRootLogin` effective-context correctness

**Why this remains open**

The audited collector uses plain `sshd -T` and a safe raw-config fallback. It does **not** yet support `sshd -T -C user=...,host=...,addr=...`, and it has no `context_specific_unknown` outcome when `Match` rules may change the effective value but connection context is unavailable.

**Required work**

- Keep plain `sshd -T` for global effective inspection.
- When safe connection context is available, support read-only `sshd -T -C user=...,host=...,addr=...`.
- If Match/context can matter and required context is missing, return UNKNOWN / `context_specific_unknown`; do not claim the global value applies to all connections.
- Keep raw fallback explicit; an absent raw directive stays UNKNOWN.
- Restrict `permit_root_login` to known OpenSSH values or UNKNOWN and expose source/status.

**DONE when**

- Tool tests cover global, context-specific, insufficient-context, and raw-fallback cases.

---

## GA2-R4 — User-supplied/self-contained reasoning path

**Why this remains open**

The current H02 tests mostly assert properties of input strings rather than proving the agent avoids collectors. The calculator handles safe expression syntax but not the required Vietnamese/English natural-language arithmetic forms. The H05 logic tests currently evaluate a helper defined inside the test file, not production runtime logic.

**Required work**

- Add an explicit self-contained/user-supplied response path that does not collect local evidence unless the user asks for live comparison.
- Runtime-test rewrite/summarize of supplied values, supplied arithmetic, comparison of two supplied values, and hypothetical config analysis with zero environment/tool execution.
- Add contrasting runtime test: supplied value vs live target explicitly requested => collection allowed.
- Extend deterministic arithmetic to at least:
  - average of 20/40/60 => 40;
  - `64 GB total, 18 GB used` => 46 GB remaining;
  - “20 + 40 + 60 then divide by 3” => 40;
  - 99.9% availability over a supplied period => deterministic downtime;
  - missing period/input => explicit insufficient-input response, not guessing.
- Implement production runtime logic classification for narrow premise/conclusion cases: `ENTAILED`, `CONTRADICTED`, `NOT_ENOUGH_INFORMATION`.
- Support direct entailment, direct contradiction, simple universal -> named instance, unrelated conclusion, and safe unsupported/ambiguous fallthrough.

**DONE when**

- Tests exercise production modules and real agent paths; no logic/arithmetic acceptance is proved by a helper that exists only in a test file.

---

## GA2-R5 — Generated artifact validation in real runtime

**Why this remains open**

`ConfigValidator` and tests for YAML/GitHub Actions/shell exist, but the audited `DeterministicAgent` does not import/use the validator in the actual generated-artifact response path. Current tests therefore prove validator behavior, not generation integration.

**Required work**

- Detect supported generated artifact type deterministically from request/output.
- Validate generated content before final response.
- If invalid and a deterministic/local repair is safe, repair once and revalidate once.
- Otherwise return the candidate with a precise validation warning; never claim it is valid.
- Keep validation metadata in trace/debug when possible.
- GitHub Actions coverage must include invalid YAML, bad cron, nonexistent step outputs, false sequential setup pretending to be a matrix, and duplicate/contradictory jobs when deterministically detectable.
- Shell validation must be syntax-only/non-executing, surface malformed snippets, preserve mutation warnings, and never turn content generation into execution authorization.

**DONE when**

- At least one agent-level generated YAML/GitHub Actions case and one generated shell case prove the validator is invoked on the actual model output before it reaches the user.

---

## GA2-R6 — Unified response strategy + final output boundary

**Why this remains open**

Answer strategy exists in traces, but response behavior is still distributed across many early-return branches. Repetition protection is currently called in several model-generated paths rather than one universal finalizer. SHORT behavior is not proven across every response strategy. This is the remaining integration point behind legacy H03/H10/H12.

**Required work**

- Define explicit response construction strategies for:
  - general explanation;
  - translation/rewrite;
  - self-contained reasoning;
  - live environment facts/assessment;
  - external verification;
  - provenance;
  - multi-source comparison;
  - code/config generation;
  - clarification/refusal.
- Reuse existing semantic routing; do not create a second intent classifier just for response formatting.
- Create one final user-visible text finalizer with an explicit order for sanitization, language quality, repetition/degeneration recovery, concise shaping, and required provenance/warnings.
- Apply the finalizer to model and deterministic user-visible paths where appropriate, including provenance/refusal/generated content; never expose pre-sanitized model text.
- SHORT must work across general, live, external, provenance, refusal/fallback without rerunning collectors and without deleting UNKNOWN/warnings/source provenance.
- RAW and EXPLAIN_PREVIOUS remain separate semantics.

**DONE when**

- Table-driven agent tests cover each major strategy and prove the universal finalizer cannot be bypassed by an early return.
- Normal structured repetition in code/config is not falsely truncated.

---

## GA2-R7 — Response/token/latency budgets + metrics

**Why this remains open**

Global provider `max_tokens` and timing fields already exist, but there is no clear per-response-strategy budget policy or response-size/token-budget metadata suitable for acceptance reporting.

**Required work**

- Define bounded output policy by major response strategy; code/config generation may have a larger budget than concise chat/refusal.
- Avoid unnecessary collector/model rounds for stable general/self-contained requests.
- Record response-size and budget metadata alongside existing duration/tool-call metrics.
- Ensure metrics support median/p95 aggregation in QA reports.
- Never improve latency by skipping grounding, source/target checks, sanitization, or validators.

**DONE when**

- Strategy-budget tests and QA metric tests pass and full suite shows no safety/grounding regression.

---

## GA2-R8 — Fresh 386 runtime acceptance + manual grading

**Why this remains open**

The latest checked-in verification evidence references an older 386-case run and is marked `PENDING_MANUAL_REVIEW`. The current 1918-test snapshot is newer, so release acceptance must be rerun on the final clean commit.

**Required work**

1. Clean worktree and record final Git SHA.
2. Run `qa-smoke`.
3. Run fresh `qa-full` with exactly 386 cases.
4. Confirm automated P0 invariant gate passes with zero violations.
5. Manually grade the 386 runtime answers using the documented PASS/PARTIAL/FAIL rubric.
6. Review answer quality specifically for:
   - current-version/date/price/identity grounding;
   - URL factual questions;
   - source-restricted comparisons;
   - user-supplied-data/self-contained reasoning;
   - generated config/shell validation;
   - concise/provenance/refusal paths;
   - language quality/repetition;
   - latency outliers.
7. Update `GA2_VERIFICATION_EVIDENCE.md` with the final run artifact, SHA, clean-worktree state, automated gates, and manual score.

**DONE when**

- Final clean-SHA 386 artifact exists.
- Automated P0 gates pass.
- Manual grading meets the GA2 release threshold.
- No release claim depends only on `pytest` being green.

## 4. Backlog growth control

Do not create `GA2-R9`, new task packets, or another continuation backlog for ordinary defects discovered while closing R1-R8.

Use this rule:

- external/web/grounding defect -> R1;
- source comparison/provenance defect -> R2;
- SSH effective-config defect -> R3;
- supplied-data/arithmetic/logic defect -> R4;
- generated artifact correctness defect -> R5;
- response routing/finalization/concise/repetition defect -> R6;
- latency/token/metrics defect -> R7;
- benchmark/manual acceptance defect -> R8.

Create a new backlog item only for a genuinely new product capability or architecture change outside GA2 scope, and only after maintainer approval.

## 5. Repository cleanup

After this file is committed as `docs/project/GA2_BACKLOG.md`, the following legacy backlog files may be removed from the working tree because Git history already preserves them:

```text
docs/project/BACKLOG.md
docs/project/DETERMINISTIC_REASONING_BACKLOG.md
docs/project/GA2_CONTINUATION_BACKLOG.md
docs/project/GA2_CONTINUATION_BACKLOG_5C30BB3D2FBD.md
docs/project/GA2_FULL_386_RUNTIME_ACCEPTANCE_BACKLOG.md
docs/project/GENERAL_AGENT_EXTERNAL_VERIFICATION_BACKLOG.md
docs/project/IMPLEMENTATION_BACKLOG.md
docs/project/ga2_tasks/
```

Keep:

```text
docs/project/GA2_BACKLOG.md
docs/project/GA2_VERIFICATION_EVIDENCE.md
```

Also keep non-backlog architecture/ADR/operator documentation unless separately reviewed as obsolete.

### Reference cleanup after deleting legacy backlog files

At minimum, update the active-backlog pointer in:

```text
docs/project/README.md
docs/ai/08_PROJECT_STATE.md
```

The snapshot also contains historical references to old backlog filenames in comments/docs such as `src/pipeline/execution_trace.py`, `scripts/qa/run_baseline.py`, `tests/qa/test_golden_schema.py`, `docs/ai/10_PHASE6_PLAN.md`, `docs/adr/ADR-0010-deterministic-external-verification.md`, and `CHANGELOG.md`. They do not change runtime behavior, but clean or reword them if you want zero dead documentation links after the deletion.
