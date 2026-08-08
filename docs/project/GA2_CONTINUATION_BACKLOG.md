# Orion — GA2 Continuation / Completion Backlog

> **Status:** Active — replaces the previous continuation backlog  
> **Checkpoint audited:** `081efc393dc2`  
> **Basis:** source audit of checkpoint `081efc393dc2` + original 386-case GA2 acceptance contract  
> **Supersedes:** `GA2_CONTINUATION_BACKLOG_5C30BB3D2FBD.md` and any self-reported DONE/PARTIAL status written by the coding model after that checkpoint  
> **Purpose:** finish only the remaining GA2 implementation, repair the canonical QA orchestration, then return control to the maintainer for smoke/full runtime acceptance.

---

# 0. Executive state

The repository is no longer near the original GA1 state. A large portion of GA2 exists and must be preserved. However, the checkpoint also contains several modules that are present and unit-tested but are not fully wired into the runtime path, plus a broken `qa-full` orchestration contract.

This backlog therefore uses a conservative source-audit classification:

| Epic | DONE | PARTIAL | TODO |
|---|---:|---:|---:|
| A — Unified QA | 8 | 3 | 0 |
| B — Output safety | 6 | 0 | 0 |
| C — Semantic routing | 8 | 2 | 0 |
| D — Target/context | 7 | 2 | 0 |
| E — Source/provenance | 5 | 3 | 0 |
| F — Internet/URL | 6 | 4 | 0 |
| G — Local collectors | 8 | 1 | 0 |
| H — Answer quality | 2 | 8 | 2 |
| **TOTAL** | **50** | **23** | **2** |

Meaning:

```text
DONE     = implementation exists, is integrated enough to preserve, and has credible regression coverage
PARTIAL  = code may exist, but original GA2 runtime contract is not fully satisfied
TODO     = required behavior is still materially absent
```

This is an **implementation planning snapshot**, not a release verdict.

The final GA2 release state remains:

```text
implementation acceptance  = NOT COMPLETE
final-code qa-smoke         = NOT YET RUN BY MAINTAINER
final-code qa-full 386      = NOT YET COMPLETE
manual behavioral grading  = NOT YET COMPLETE
GA2 release acceptance      = NOT COMPLETE
```

The old 386 run cannot be used as final evidence because the source changed afterward. The later final-code 386 rerun was interrupted before completion.

---

# 1. Mandatory execution policy

This section is authoritative for the coding agent.

## 1.1 Source of truth

Work only from:

```text
docs/project/GA2_CONTINUATION_BACKLOG.md
```

Treat task status in this file as authoritative for continuation work.

Do **not** infer completion from:

- previous chat context,
- previous model summaries,
- `docs/ai/08_PROJECT_STATE.md` status claims alone,
- comments saying a task is DONE,
- existence of a module without runtime integration,
- passing unit tests that only test helper code in isolation.

For every `PARTIAL` or `TODO` item, inspect the actual runtime path before marking it complete.

## 1.2 Coding agent may

The coding agent MAY:

- inspect source/tests/docs,
- edit code,
- add deterministic unit/integration tests,
- run targeted pytest files,
- run `ruff` on changed files,
- run typecheck when useful,
- run the normal repository pytest suite once at the end if practical,
- run dry-run/list/help modes of QA tooling that do not start the runtime or consume model quota.

## 1.3 Coding agent must not

During implementation, the coding agent MUST NOT automatically run:

```text
make qa-smoke
make qa-full
scripts/qa/ga2_runner.py --mode full
orion_qa_runner.py over all 386 questions
docker compose up --build solely to benchmark the model
benchmark -> fix -> benchmark -> fix loops
```

Do not consume runtime/model quota during coding.

## 1.4 Stop condition

After implementation work is complete:

```text
code complete
→ targeted tests pass
→ typecheck / ruff / repository pytest as appropriate
→ git diff --check
→ report exact task IDs DONE / PARTIAL / BLOCKED
→ STOP
```

The maintainer will manually run runtime acceptance later.

## 1.5 No self-declared GA2 completion

The coding agent must not mark GA2 complete from:

- HTTP 200 responses,
- `P0 = 0` smoke output alone,
- unit-test success alone,
- transport success,
- a partially completed 386 run,
- an ungraded full runtime transcript.

GA2 completion belongs to the maintainer stage after final 386 grading.

---

# 2. Implemented guardrails that must not regress

The following are already valuable and should be treated as protected behavior.

## 2.1 Output safety

Preserve:

- `<think>` / hidden-reasoning sanitization,
- hidden/system-prompt refusal,
- API key/password/private-key/credential refusal,
- final API-boundary sanitation,
- mixed CJK/Cyrillic contamination filtering for normal Vietnamese/English output,
- language-aware deterministic refusals.

## 2.2 Explicit-target safety

Preserve the invariant:

```text
explicit_target != null
AND target_resolution != RESOLVED
=> environment_execution_steps == []
```

No new planner/context path may reintroduce localhost fallback for an unresolved explicit target.

## 2.3 Source safety

Preserve typed source restrictions and execution-time forbidden-source assertions.

A hard restriction such as:

```text
Grafana only
Zabbix only
SSH only
Linux only
```

must never silently become `ANY`.

## 2.4 Internet security

Preserve:

- private/loopback/link-local URL blocking,
- redirect target revalidation,
- mixed public/private DNS rejection,
- DNS-rebinding protection,
- bounded fetches,
- precise unsupported/empty/extraction failure states,
- provider-unavailable fail-closed behavior.

## 2.5 Evidence grounding

Preserve the distinction between:

```text
FETCH_SUCCESS
CONTENT_EXTRACTED
CONTENT_EMPTY
CONTENT_UNSUPPORTED
CONTENT_TRUNCATED
CONTENT_BLOCKED
EXTRACTION_FAILED
```

and do not equate fetch success with sufficient evidence.

## 2.6 Frozen QA baseline

Preserve the 386-case baseline:

| Suite | Cases |
|---|---:|
| DEFAULT | 193 |
| Core / `cauhoi_kiemtra_v2` | 66 |
| Part B | 28 |
| Adversarial | 61 |
| Workflow | 38 |
| **TOTAL** | **386** |

---

# 3. GA2 task status index

Legend:

```text
DONE     = preserve; add regression only when touched
PARTIAL  = finish implementation/integration
TODO     = implement
```

## EPIC A — QA runtime attestation and unified runner

| ID | Pri | Status | Task |
|---|---|---|---|
| GA2-A01 | P0 | DONE | Freeze 386 cases with stable IDs |
| GA2-A02 | P0 | DONE | Record git SHA, dirty state, runtime image/container, flags, runner version |
| GA2-A03 | P0 | DONE | QA tooling can build/start intended Docker runtime |
| GA2-A04 | P0 | DONE | Canonical `make qa-smoke` target exists |
| GA2-A05 | P0 | DONE | Canonical `make qa-full` target exists |
| GA2-A06 | P0 | PARTIAL | `qa-full` orchestration exists but stage handoff/run-dir/exit propagation are not correct |
| GA2-A07 | P1 | DONE | Full Q&A baseline is exactly 386 cases |
| GA2-A08 | P1 | DONE | Timestamp/SHA run directories preserve history |
| GA2-A09 | P0 | PARTIAL | Unified report/artifact contract is not correctly wired to actual Q&A outputs |
| GA2-A10 | P1 | PARTIAL | Regression comparison exists but must operate on complete canonical run artifacts |
| GA2-A11 | P1 | DONE | Smoke fail-fast P0 mode + full diagnostic mode |

## EPIC B — Output safety boundary

| ID | Pri | Status | Task |
|---|---|---|---|
| GA2-B01 | P0 | DONE | Hidden reasoning output boundary |
| GA2-B02 | P0 | DONE | Hidden/system prompt refusal |
| GA2-B03 | P0 | DONE | API key/password/private-key refusal |
| GA2-B04 | P0 | DONE | Sensitive credential-file refusal |
| GA2-B05 | P0 | DONE | Existing user-visible output paths use the final response sanitizer |
| GA2-B06 | P1 | DONE | Refusals preserve Vietnamese/English response language |

## EPIC C — Semantic routing and planning

| ID | Pri | Status | Task |
|---|---|---|---|
| GA2-C01 | P1 | DONE | `model/provider` no longer collides with forecast/time-model routing |
| GA2-C02 | P1 | DONE | Greeting/thanks/capability/identity/meta use non-infra routing |
| GA2-C03 | P1 | DONE | Conceptual process/service/network/storage questions avoid accidental infra execution |
| GA2-C04 | P1 | DONE | Translation/rewrite bypass infra collection |
| GA2-C05 | P1 | DONE | Self-contained supplied-data transformations bypass live collectors |
| GA2-C06 | P1 | DONE | Current/news/weather/price/current-version use common external policy |
| GA2-C07 | P1 | PARTIAL | Compound current-information dependency is detected, but full dependent execution/generation is not complete |
| GA2-C08 | P1 | DONE | URL literal in requested code/config does not automatically authorize fetch |
| GA2-C09 | P1 | DONE | Reboot-status wording is read-only rather than mutation |
| GA2-C10 | P1 | PARTIAL | Multi-intent planner exists but is not integrated into the real agent/execution path |

## EPIC D — Target and conversation state

| ID | Pri | Status | Task |
|---|---|---|---|
| GA2-D01 | P0 | DONE | Unknown explicit target -> zero environment execution |
| GA2-D02 | P0 | DONE | Execution-target assertion |
| GA2-D03 | P1 | DONE | Registered aliases such as `monitor` resolve deterministically |
| GA2-D04 | P1 | DONE | Active target can persist across valid follow-ups |
| GA2-D05 | P1 | DONE | Local evidence is not carried into unresolved remote-target conversation |
| GA2-D06 | P1 | DONE | Explicit target/context reset path |
| GA2-D07 | P1 | PARTIAL | Correction framework exists, but `Không phải CPU, tôi hỏi RAM` can still resolve to CPU |
| GA2-D08 | P1 | PARTIAL | Answer-shape state exists, but RAW/EXPLAIN_PREVIOUS are not fully applied to runtime response construction |
| GA2-D09 | P1 | DONE | Vague referents fail safe/clarify rather than guessing localhost |

## EPIC E — Source constraints and provenance

| ID | Pri | Status | Task |
|---|---|---|---|
| GA2-E01 | P0 | DONE | Immutable typed source fields |
| GA2-E02 | P0 | PARTIAL | Preserve source restrictions through clarification and follow-up state transitions |
| GA2-E03 | P0 | DONE | Execution-time forbidden-source assertion |
| GA2-E04 | P1 | PARTIAL | Multi-source comparison must preserve each requested source independently end-to-end |
| GA2-E05 | P1 | DONE | Separate provenance for Linux/SSH/Grafana/Zabbix facts |
| GA2-E06 | P1 | DONE | Avoid meaningless timeframe request for point-in-time comparisons |
| GA2-E07 | P1 | DONE | Precise source-unavailable state without fallback |
| GA2-E08 | P1 | PARTIAL | Provenance responder is wired, but currently derives from source constraints rather than actual prior evidence receipts |

## EPIC F — Internet/search/URL grounding

| ID | Pri | Status | Task |
|---|---|---|---|
| GA2-F01 | P0 | DONE | Search query validation is data-oriented, not shell-oriented |
| GA2-F02 | P0 | DONE | Raw search query is not interpolated into shell execution |
| GA2-F03 | P0 | DONE | Fetch success and content extraction are separate states |
| GA2-F04 | P0 | PARTIAL | Bounded extraction exists; request-relevant evidence selection still needs completion |
| GA2-F05 | P0 | PARTIAL | Current-claim validator exists but remains narrow/regex-oriented rather than general claim-to-source grounding |
| GA2-F06 | P0 | DONE | No usable content -> evidence cannot remain `SUFFICIENT` |
| GA2-F07 | P1 | PARTIAL | Provider-unavailable response exists, but compound/multi-intent routes must converge on it after C07/C10 are integrated |
| GA2-F08 | P1 | DONE | SSRF/private-IP/redirect/DNS-rebinding controls preserved |
| GA2-F09 | P1 | DONE | Redirect-to-private regression coverage |
| GA2-F10 | P1 | PARTIAL | Complete content-type/timeout/DNS/empty/oversize/encoding failure matrix |

## EPIC G — Local read-only evidence

| ID | Pri | Status | Task |
|---|---|---|---|
| GA2-G01 | P1 | DONE | Filesystem usage facts |
| GA2-G02 | P1 | DONE | Uptime / boot-time fact |
| GA2-G03 | P1 | DONE | Zombie detection uses process state and top CPU/RAM process facts exist |
| GA2-G04 | P1 | DONE | Active/all/failed service listing |
| GA2-G05 | P1 | DONE | Listening TCP ports |
| GA2-G06 | P1 | DONE | Docker running-container discovery / precise unavailable status |
| GA2-G07 | P1 | DONE | Firewall state |
| GA2-G08 | P1 | PARTIAL | `sshd -T` support exists; effective Match/context handling and fallback semantics still need tightening |
| GA2-G09 | P1 | DONE | Metric -> collector mapping regression matrix |

## EPIC H — Grounded answer quality

| ID | Pri | Status | Task |
|---|---|---|---|
| GA2-H01 | P1 | DONE | Missing evidence remains UNKNOWN instead of becoming unsupported high risk |
| GA2-H02 | P1 | PARTIAL | User-supplied data protection needs broader end-to-end coverage |
| GA2-H03 | P1 | PARTIAL | Request-appropriate response strategy/templates need broader runtime coverage |
| GA2-H04 | P2 | PARTIAL | Basic calculator module exists, but natural-language arithmetic benchmark forms are not fully supported |
| GA2-H05 | P2 | TODO | Logical inference behavior is not implemented in Orion runtime; current helper exists only in tests |
| GA2-H06 | P2 | PARTIAL | Config validator exists but is not integrated into generated code/config response path |
| GA2-H07 | P2 | PARTIAL | GitHub Actions/YAML structural validation exists in helper code but is not runtime-integrated |
| GA2-H08 | P2 | PARTIAL | Shell syntax validation exists in helper code but is not runtime-integrated |
| GA2-H09 | P2 | DONE | Accidental mixed-script contamination detection |
| GA2-H10 | P2 | PARTIAL | Concise mode works partially; integrate cleanly with D08 across response strategies |
| GA2-H11 | P2 | TODO | Stable-general latency/token-budget reduction |
| GA2-H12 | P2 | PARTIAL | Repetition detector exists but is not a universal final-output boundary |

---

# 4. Detailed remaining implementation tasks

Only `PARTIAL` and `TODO` items below require new implementation work. `DONE` items are preserve/regression-only unless a remaining task touches them.

---

## GA2-A06 — Repair the canonical `qa-full` orchestrator

### Current implementation

`make qa-full` now calls:

```text
scripts/qa/unified_qa.py
```

and the intended stage list includes:

```text
typecheck
ruff
pytest
run_tests_v2
run_baseline
run_acceptance
docker build/start
runtime attestation
386 Q&A
aggregate report
comparison
```

That architecture is correct in principle, but the current wiring is not release-safe.

### Confirmed gaps

#### Gap A — baseline artifact handoff is wrong

`run_baseline.py --smoke` supports `--output-dir`, but `unified_qa.py` does not supply a run-local output directory and later searches only:

```text
<run_dir>/baseline_*.json
```

The baseline smoke path can instead create `smoke_*.json` under its own default output directory.

Result: `run_acceptance` may not receive the baseline report produced by the previous stage.

#### Gap B — unified runner and Q&A runner own different run directories

`unified_qa.py` creates:

```text
artifacts/qa/runs/<RUN_A>/
```

then calls `ga2_runner.py --output-root <RUN_A>`.

`ga2_runner.py` creates another timestamp/SHA directory inside that root:

```text
artifacts/qa/runs/<RUN_A>/<RUN_B>/
```

The unified orchestrator then looks for Q&A artifacts in `RUN_A`, not `RUN_B`.

#### Gap C — Q&A exit code is ignored

The Q&A subprocess result is currently launched but not used to determine final `qa-full` exit status.

A P0 failure, runner crash, or nonzero Q&A result must not be hidden by a final zero exit from the unified wrapper.

### Required implementation

Make the unified orchestrator the **single owner of the run ID/run directory**.

Preferred contract:

```text
unified_qa creates run_dir once
→ every technical stage writes/copies artifacts under that run_dir
→ ga2_runner receives an explicit existing run_dir mode
→ ga2_runner does NOT create a child timestamp/SHA directory in unified mode
→ aggregate reads exactly that run_dir
```

Acceptable implementation options:

1. add `ga2_runner --run-dir <existing_dir>`, while keeping `--output-root` for standalone mode; or
2. expose an in-process runner function that writes into the unified run directory.

For baseline/acceptance:

```text
run_baseline.py --output-dir <run_dir>/baseline
→ capture exact produced JSON path
→ run_acceptance.py --report <that_exact_json>
                --output-dir <run_dir>/acceptance
```

Do not discover the handoff by loose globbing when the previous stage can return/record the exact artifact path.

### Exit-code contract

`make qa-full` must be nonzero when any required stage fails.

At minimum:

```text
required technical stage nonzero -> qa-full nonzero
Docker build/start failure       -> qa-full nonzero
Q&A runner P0/runner failure      -> qa-full nonzero
aggregate/report write failure    -> qa-full nonzero
manual grading pending            -> explicit documented policy, not accidental exit behavior
```

If the design intentionally uses a special nonzero exit for `PENDING_MANUAL_REVIEW`, document it and unit-test it. Do not mix “manual review pending” with “technical runner crashed”.

### Tests

Add unit/integration tests that use temporary directories and stubbed subprocesses. Do not launch Docker/model runtime.

Test at least:

- exact stage order,
- baseline output-dir wiring,
- acceptance receives exact baseline JSON path,
- Q&A writes into same run directory,
- no nested run directory,
- Q&A nonzero propagates,
- technical failure propagates,
- optional/required stage policy is explicit.

### Acceptance

```text
one qa-full invocation
= one run_id
= one canonical run directory
= all stage artifacts under that directory
= deterministic nonzero status on required failure
```

---

## GA2-A09 — Repair unified artifact/report contract

### Confirmed gaps

The unified report expects canonical transcript names:

```text
default_193.md
cauhoi_kiemtra_v2.md
cauhoi_phanb.md
cauhoi_v4_adversarial.md
cauhoi_v5_workflow.md
```

but `ga2_runner.py` currently writes names derived from internal suite labels such as:

```text
default.md
core.md
part_b.md
adversarial.md
workflow.md
```

Combined with the nested run-dir bug, `transcripts` status in the aggregate can be false even when the Q&A runner wrote files elsewhere.

### Required implementation

Use one canonical filename mapping shared by both runners.

Expected artifacts:

```text
manifest.json
technical/
integration/
baseline/
acceptance/
default_193.md
cauhoi_kiemtra_v2.md
cauhoi_phanb.md
cauhoi_v4_adversarial.md
cauhoi_v5_workflow.md
qa_summary.json
regression.json
summary.json
summary.md
```

Avoid having both the Q&A runner and unified runner overwrite the same `summary.json` with incompatible schemas.

Recommended separation:

```text
qa_summary.json        # raw ga2_runner result
summary.json           # unified aggregate result
summary.md             # human unified summary
```

The unified summary must contain:

- run ID,
- git SHA/dirty state,
- runtime image/container/flags,
- each technical stage and exit code,
- 386 suite counts,
- P0 count,
- transcript presence,
- latency statistics,
- grading state,
- comparison state,
- artifact paths.

### Acceptance

A test fixture representing a complete 386 run must produce all five canonical transcript-presence flags as true and must not depend on nested directories.

---

## GA2-A10 — Make regression comparison operate only on canonical completed runs

### Current state

A comparison helper exists, but the source run may currently be missing the actual Q&A summary due A06/A09 path problems.

### Required implementation

After A06/A09 are repaired:

- compare unified summaries from canonical run directories,
- distinguish incomplete/interrupted runs from complete runs,
- never compare an aggregate wrapper that has `qa=None` as though it were a valid 386 baseline,
- never auto-promote an ungraded run.

At minimum compare:

```text
case_count
P0_count
PASS/PARTIAL/FAIL once grades exist
weighted score once grades exist
median/p95 latency
routing/target/source/evidence regressions where structured metadata exists
```

### Acceptance

Comparison against an incomplete run must produce:

```text
comparison_status = INCOMPLETE_BASELINE | NOT_COMPARABLE
```

rather than numeric fake improvement/regression values.

---

## GA2-C07 — Finish current-information dependency inside compound tasks

### Current state

The request classifier now correctly recognizes examples such as:

```text
Tìm phiên bản Python mới nhất rồi viết Dockerfile dùng phiên bản đó.
```

as requiring external verification.

That is an improvement, but it is not yet the full original contract.

### Required behavior

Represent and execute the dependency explicitly:

```text
STEP 1: EXTERNAL_VERIFICATION(current Python version)
STEP 2: CONTENT_GENERATION(Dockerfile, depends_on=STEP 1 verified value)
```

Required rules:

- Step 2 must use the verified value from Step 1, not model memory.
- If Step 1 is unavailable/unsupported, do not invent a concrete version.
- A degraded result may use a clearly unresolved parameter such as `${PYTHON_VERSION}` if appropriate.
- Source/target constraints from the external step must not leak incorrectly into unrelated generation semantics.

### Acceptance tests

- current Python -> Dockerfile,
- current Kubernetes -> config snippet,
- provider unavailable -> no concrete current version fabricated,
- fetched evidence without the requested version -> no concrete version fabricated.

---

## GA2-C10 — Integrate `MultiIntentPlanner` into runtime

### Current state

`src/pipeline/multi_intent_planner.py` exists and has unit tests.

Source audit shows the production runtime does not currently call `MultiIntentPlanner`; references are limited to the module/tests.

Therefore helper existence does not satisfy C10.

### Required integration

The actual agent/request pipeline must construct and consume ordered plans for true multi-intent requests.

Examples:

```text
Giải thích RAM là gì rồi kiểm tra RAM trên monitor.
Tìm phiên bản hiện tại rồi tạo config dùng phiên bản đó.
Kiểm tra CPU rồi RAM trên monitor.
```

Plan properties:

- ordered steps,
- typed step kinds,
- target per step,
- source constraints per step,
- explicit dependencies,
- failure/blocked propagation,
- no unrelated fallback step.

Do not create unrestricted ReAct/tool-selection behavior. Planning remains deterministic.

### Acceptance

A runtime-level test must prove that the agent consumes the plan, not merely that the planner object can produce one.

---

## GA2-D07 — Fix correction semantics

### Confirmed failing example

```text
Không phải CPU, tôi hỏi RAM.
```

The current correction helper can scan for `cpu` first and return CPU even though CPU is explicitly negated.

A test that accepts either CPU or RAM is not valid coverage.

### Required parser behavior

Correction semantics must distinguish:

```text
negated concept
replacement concept
```

Examples:

```text
Không phải CPU, tôi hỏi RAM.       -> RAM
Ý tôi là disk, không phải memory.  -> DISK
Not CPU, memory.                   -> MEMORY
```

Required state transition:

```text
active_concept = old
correction(old -> new)
active_concept = new
```

Do not union old + new.

### Tests

Assertions must require the exact corrected concept.

Do not use permissive assertions such as:

```python
assert corrected in {"cpu", "ram"}
```

when only RAM is semantically correct.

---

## GA2-D08 — Finish RAW / SHORT / EXPLAIN_PREVIOUS runtime behavior

### Current state

Conversation state supports:

```text
DEFAULT
SHORT
RAW
EXPLAIN_PREVIOUS
```

but runtime response construction clearly applies SHORT more completely than RAW/EXPLAIN_PREVIOUS.

### Required behavior

#### SHORT

- reduce boilerplate,
- preserve critical warning/refusal/uncertainty/provenance.

#### RAW

For evidence-backed environment requests, return compact structured/raw facts rather than assessment prose.

Do not bypass source/target safety.

#### EXPLAIN_PREVIOUS

Explain the previous resolved answer/evidence, not a newly invented environment request.

Do not rerun collectors unless the user explicitly asks for a refresh.

### Acceptance tests

Use a multi-turn agent-level test, not only state-parser tests:

```text
turn 1: inspect memory on monitor
turn 2: raw data only
turn 3: explain previous answer
```

Verify response strategy and tool execution counts.

---

## GA2-E02 — Preserve hard source constraints through conversation state

### Required invariant

```text
initial hard source restriction
→ clarification
→ clarification answer
→ follow-up
=> same hard restriction unless user explicitly changes/resets it
```

Example:

```text
User: Chỉ dùng Grafana kiểm tra CPU.
Orion: target nào?
User: monitor.
```

Resolved request must still be Grafana-only.

### Acceptance tests

- Grafana-only + target clarification,
- Zabbix-only + metric follow-up,
- SSH-only + short/raw follow-up,
- explicit source reset/change,
- no accidental `ANY` conversion.

---

## GA2-E04 — Complete multi-source comparison contract

### Required representation

For:

```text
So sánh CPU từ Grafana và Zabbix trên monitor.
```

preserve at least:

```text
requested_sources = [GRAFANA, ZABBIX]
facts:
  - source: GRAFANA
  - source: ZABBIX
comparison_status = COMPLETE | PARTIAL | UNAVAILABLE
```

Rules:

- never collapse to `ANY`,
- never silently substitute Linux/SSH for a missing requested source,
- if one source fails, return PARTIAL with explicit missing source,
- keep provenance attached to each side of the comparison.

This may share planning infrastructure with C10 but source-policy semantics remain deterministic and immutable.

---

## GA2-E08 — Answer provenance questions from actual evidence receipts

### Current bug

`ProvenanceResponder` is wired into the agent, but currently derives source information primarily from active source constraints.

Source constraints describe what the user allowed/requested; they are not proof of what tools/evidence were actually used.

Example problem:

```text
User asks a normal local fact without saying "Linux only".
Orion actually uses Linux collector.
User asks: "Nguồn dữ liệu nào vừa được dùng?"
```

The answer must report the actual Linux evidence/tool receipt even though no source constraint was set.

### Required session metadata

Persist a compact previous-response evidence receipt, e.g.:

```text
previous_evidence_receipts = [
  {
    source,
    tool,
    target,
    capability,
    fact_ids,
    status,
    timestamp
  }
]
```

Do not store hidden chain-of-thought.

### Required answers

Support:

```text
Nguồn dữ liệu nào vừa được dùng?
Câu trước lấy số liệu từ đâu?
Did you use Grafana or SSH?
```

Answer from actual receipts, including partial/unavailable source states where relevant.

---

## GA2-F04 — Request-relevant web evidence extraction

### Current state

Bounded content extraction exists, which is necessary but not sufficient.

A successfully extracted page can still contain mostly navigation/footer/unrelated text.

### Required implementation

Before a page can satisfy an external claim:

- retain URL/title/content status,
- tokenize/normalize request entities and claim type,
- select bounded passages relevant to those entities,
- preserve passage/source association,
- distinguish “content extracted” from “relevant evidence found”.

Suggested typed state:

```text
CONTENT_EXTRACTED
RELEVANT_EVIDENCE_FOUND
RELEVANT_EVIDENCE_NOT_FOUND
```

Do not let page navigation text satisfy current-version/date/price requests.

---

## GA2-F05 — General claim-to-source grounding

### Current state

The current claim validator catches some exact version/date/price patterns, but it is too narrow to be the general grounding contract.

### Required minimum claim classes

Ground at least:

- current software version,
- release date,
- current price/value,
- current office holder/identity,
- simple factual claim explicitly requested from a supplied URL.

### Required invariant

A concrete current claim must be traceable to extracted relevant evidence.

If not:

```text
UNKNOWN
```

or an explicit inability statement.

Do not use model memory to fill a missing exact value and then attach a provenance footer.

### Tests

Include negative cases where:

- page fetch succeeds but value is absent,
- page contains an old version but query asks latest,
- page date is ambiguous,
- current identity is not present in extracted passages.

---

## GA2-F07 — Unify provider-unavailable behavior after compound planning is integrated

A deterministic unavailable response exists for simple external requests.

After C07/C10 are wired, verify the same fail-closed behavior for:

```text
simple current query
news/weather/current value
external step inside compound generation
multi-intent workflow
```

No compound path may fall through to stale model knowledge.

---

## GA2-F10 — Complete external failure-state matrix

Add deterministic tests for at least:

```text
unsupported MIME/content type
timeout
DNS failure
HTTP 404
HTTP 500
empty body
oversized body
invalid/odd encoding
redirect chain
mixed public/private DNS
redirect public -> private
```

Each case must yield a typed state and must not become sufficient evidence accidentally.

Preserve all existing SSRF/rebinding defenses.

---

## GA2-G08 — Tighten effective SSH `PermitRootLogin`

### Current state

`sshd -T` support exists, which is much better than raw file parsing.

### Remaining work

Define the contract for effective configuration when `Match` blocks or context-sensitive rules apply.

If Orion has enough safe context to evaluate a specific connection context, prefer a read-only form equivalent to:

```text
sshd -T -C user=...,host=...,addr=...
```

where appropriate and available.

Otherwise explicitly distinguish:

```text
global_effective_config
context_specific_unknown
raw_config_fallback
unavailable
```

Required output:

```text
permit_root_login = yes | no | prohibit-password | forced-commands-only | UNKNOWN
source = effective_sshd_config | raw_config_fallback | unavailable
```

Do not report `no` simply because a directive is absent.

---

## GA2-H02 — Make user-supplied data authoritative end-to-end

### Required behavior

For self-contained inputs such as:

```text
CPU ổn, RAM ổn, disk 92% -> rewrite this
64 GB total - 18 GB used -> how much remains?
```

Orion must use the values supplied by the user.

No local collector may overwrite them unless the user explicitly asks for a live comparison.

### Tests

Cover infra-looking supplied text so lexical routing does not trigger live collection.

Include:

- rewrite,
- summarize,
- arithmetic,
- comparison of user-provided values,
- hypothetical config analysis.

---

## GA2-H03 — Broaden request-appropriate response strategies

Remove remaining universal infra-assessment fallback behavior.

Use explicit response strategies for at least:

```text
general explanation
translation/rewrite
self-contained reasoning
live environment facts
external verification
provenance answer
multi-source comparison
code/config generation
```

A simple conceptual answer must not inherit risk/assessment sections merely because it contains an infrastructure noun.

Add table-driven routing/response-strategy tests.

---

## GA2-H04 — Finish deterministic basic calculator for natural-language benchmark forms

### Current state

`basic_calculator.py` exists and supports narrow arithmetic forms.

### Remaining behavior

Support common natural-language forms in Vietnamese/English without turning the feature into a code evaluator.

Minimum examples:

```text
Tính trung bình của 20, 40, 60. -> 40
64 GB tổng, đã dùng 18 GB, còn bao nhiêu? -> 46 GB
20 + 40 + 60 rồi chia 3 -> 40
99.9% availability trong 30 ngày -> deterministic downtime calculation
```

Rules:

- parse only a narrow safe grammar,
- preserve units when obvious,
- ask when required period/input is missing,
- never execute arbitrary Python/shell.

---

## GA2-H05 — Implement basic logical inference behavior in runtime

### Current gap

The checkpoint contains a simple logic helper in tests, not in the Orion runtime path.

Testing a helper defined inside a test file does not satisfy H05.

### Scope

Do not build a theorem prover.

Implement a narrow deterministic classification for simple benchmark-style premise/conclusion tasks:

```text
ENTAILED
CONTRADICTED
NOT_ENOUGH_INFORMATION
```

At minimum prevent the earlier obvious error where a conclusion is asserted despite not following from the premises.

### Tests

- direct entailment,
- direct contradiction,
- existential/universal non-entailment,
- unrelated conclusion,
- ambiguous natural-language case falls back safely rather than fabricating certainty.

---

## GA2-H06 — Integrate config self-check into generated-artifact response path

### Current state

`ConfigValidator` exists but source audit does not show it being called by the actual code/config generation path.

### Required integration

Before returning generated technical config where a supported validator exists:

```text
generate candidate
→ safe non-executing validation
→ if valid: return
→ if invalid and deterministically repairable: repair + revalidate once
→ otherwise return candidate with precise validation warning/error
```

Do not create autonomous deployment/execution.

Validation metadata may be kept in trace/debug metadata rather than verbose user prose.

---

## GA2-H07 — Integrate GitHub Actions / YAML validation

Use H06 integration to validate generated YAML/workflows.

Regression cases must catch at least:

- invalid YAML,
- invalid GitHub Actions schedule syntax,
- sequential `setup-python` steps pretending to form a matrix,
- nonexistent step outputs,
- duplicate/contradictory jobs where deterministically detectable.

The validator must run on generated workflow output, not only in isolated unit tests.

---

## GA2-H08 — Integrate shell syntax validation without execution

Generated shell snippets should receive non-executing syntax validation where supported.

Rules:

- syntax validation is not authorization to execute,
- mutating commands remain generation-only unless separately authorized by existing safety policy,
- no command side effects during validation.

Add an agent-level test proving malformed generated shell is detected before final answer.

---

## GA2-H10 — Complete concise mode across response strategies

Integrate concise behavior with D08 rather than introducing a second state mechanism.

Concise mode should:

- remove unnecessary assessment boilerplate,
- preserve critical warnings,
- preserve refusal reason,
- preserve provenance when required,
- preserve uncertainty,
- avoid rerunning tools just to shorten the previous answer.

Test general, environment, external-verification, provenance and refusal responses.

---

## GA2-H11 — Add latency/token-budget controls

### Prior benchmark problem

The earlier 386 run showed long-tail latency and very large responses, including pathological general-answer payloads.

### Required deterministic controls

Add bounded policy for stable/general responses:

- response/generation budget by answer strategy,
- no unnecessary infra collector rounds for general questions,
- no unnecessary multi-model/assessment rounds,
- explicit latency metadata where practical,
- avoid giant generic assessment templates for simple requests.

Do not optimize by dropping required grounding/safety checks.

### Acceptance

Define measurable internal targets for final acceptance reporting, at least:

```text
median latency
p95 latency
max response size/token budget by major response strategy
```

Do not hard-code benchmark-specific answers.

---

## GA2-H12 — Make repetition/degeneration protection universal

### Current state

`RepetitionDetector` exists and is used on some assessment paths, but not all final user-visible paths.

### Required architecture

Repetition/degeneration checks belong at or immediately before the universal final output boundary, alongside safety/language sanitation.

Detect obvious cases such as:

```text
same sentence repeated many times
same paragraph repeated
looping fragments
large duplicated blocks
```

Required behavior:

- preserve a useful non-repeated prefix when safe,
- truncate/reject pathological tail,
- never expose hidden reasoning while recovering,
- work for general chat, external verification, assessment, refusal/fallback and generated content.

Add deterministic synthetic tests plus API-boundary tests.

---

# 5. Required regression set before handoff

These are coding-time deterministic tests. They are **not** the 386 runtime benchmark.

## QA orchestration

- unified runner uses one run ID,
- no nested Q&A run directory,
- baseline JSON exact handoff,
- acceptance output under same run,
- five canonical transcript names,
- Q&A nonzero propagates,
- interrupted/incomplete run is not treated as comparable complete run.

## Routing/planning

- `Tìm phiên bản Python mới nhất rồi viết Dockerfile dùng phiên bản đó.`
- `Viết Dockerfile tải https://example.com/app.tar.gz nhưng đừng fetch URL.`
- explanation + live check in one request,
- current lookup + generation dependency,
- multi-source compare path.

## Context

- `Không phải CPU, tôi hỏi RAM.` -> RAM exactly,
- `Ý tôi là disk, không phải memory.` -> disk exactly,
- `ngắn thôi`,
- `raw data only`,
- `giải thích câu trước`,
- ambiguous vague referent clarifies,
- no unintended collector rerun for explain-previous.

## Source/provenance

- Grafana-only survives clarification,
- Zabbix-only survives follow-up,
- Grafana+Zabbix stays two-source comparison,
- provenance question reports actual used tool/source even when no hard source constraint was specified.

## External grounding

- fetched irrelevant page is not sufficient,
- current value absent from page is not invented,
- provider unavailable inside compound task,
- unsupported MIME,
- timeout,
- DNS failure,
- empty body,
- oversized body,
- encoding edge case,
- public redirect to private blocked.

## Local evidence

- effective/global/context-specific SSH state is typed correctly,
- existing G03/G09 process/collector regressions remain green.

## Answer quality

- supplied data not replaced by localhost,
- natural-language 64 - 18,
- average 20/40/60,
- basic logical non-entailment,
- invalid GitHub Actions output caught through runtime generation path,
- malformed shell caught through runtime generation path,
- concise mode across multiple strategies,
- repetition synthetic cases at final boundary.

---

# 6. Canonical QA workflow — implement correctly, do not execute automatically

The maintainer workflow remains exactly:

```bash
make qa-smoke
```

then, only after smoke is accepted:

```bash
make qa-full
```

## 6.1 `make qa-smoke`

Expected maintainer-run flow:

```text
preflight
→ build/start intended Docker runtime once
→ health check
→ runtime attestation
→ 37 critical smoke cases
→ P0 gate
→ smoke summary
```

## 6.2 `make qa-full`

Expected maintainer-run flow:

```text
typecheck
→ ruff
→ pytest
→ run_tests_v2
→ run_baseline
→ run_acceptance
→ build/start intended Docker runtime once
→ runtime attestation
→ DEFAULT 193
→ Core 66
→ Part B 28
→ Adversarial 61
→ Workflow 38
→ total 386
→ unified report
→ previous-run comparison
→ PENDING_MANUAL_REVIEW until grades are supplied
```

Do not build/start/stop the runtime separately per suite.

---

# 7. Canonical QA artifact contract

Target structure:

```text
artifacts/qa/runs/
└── <timestamp>_<gitsha>/
    ├── manifest.json
    ├── technical/
    │   ├── typecheck.stdout.txt
    │   ├── typecheck.stderr.txt
    │   ├── ruff.stdout.txt
    │   ├── ruff.stderr.txt
    │   ├── pytest.stdout.txt
    │   └── pytest.stderr.txt
    ├── integration/
    │   └── ... run_tests_v2 artifacts ...
    ├── baseline/
    │   └── ... baseline JSON/MD ...
    ├── acceptance/
    │   └── ... acceptance JSON/MD ...
    ├── default_193.md
    ├── cauhoi_kiemtra_v2.md
    ├── cauhoi_phanb.md
    ├── cauhoi_v4_adversarial.md
    ├── cauhoi_v5_workflow.md
    ├── qa_summary.json
    ├── grades.json
    ├── regression.json
    ├── summary.json
    └── summary.md
```

Optional pointer:

```text
artifacts/qa/latest
```

or `latest.json`, but historical run directories must never be overwritten.

The manifest must describe the runtime actually tested, not only the current checkout.

---

# 8. Implementation waves

Do not jump randomly across the remaining backlog. Complete in controlled waves.

## Wave 1 — Fix QA orchestration first

```text
A06
A09
A10
```

Goal:

- one run ID,
- correct baseline -> acceptance handoff,
- no nested Q&A run,
- canonical filenames,
- correct exit propagation,
- aggregate/report contract trustworthy.

Only unit/tempdir/stubbed-subprocess tests. **Do not run qa-full.**

## Wave 2 — Finish runtime planning/context/provenance

```text
C07
C10
D07
D08
E02
E04
E08
F07
```

Goal:

- compound dependencies execute deterministically,
- multi-intent planner is actually consumed by runtime,
- corrections are exact,
- RAW/EXPLAIN previous work end-to-end,
- hard source restrictions survive turns,
- provenance uses actual evidence receipts,
- provider-unavailable behavior remains fail-closed in compound flows.

## Wave 3 — Finish external grounding

```text
F04
F05
F10
```

Goal:

- extracted content is query-relevant,
- current claims are traceable to evidence,
- failure-state matrix complete.

## Wave 4 — Finish local evidence edge semantics

```text
G08
```

Goal:

- effective SSH policy semantics are explicit and never fabricated.

## Wave 5 — Finish answer-quality runtime integration

```text
H02
H03
H04
H05
H06
H07
H08
H10
H11
H12
```

Goal:

- user data stays authoritative,
- natural-language arithmetic/logic stops misrouting,
- config/YAML/shell validators are in the actual generation path,
- concise mode is consistent,
- latency/repetition controls exist at the correct boundary.

## Wave 6 — Engineering handoff only

After all implementation waves:

```text
targeted tests
→ typecheck
→ ruff check .
→ full repository pytest once if practical
→ git diff --check
→ task-status report
→ STOP
```

Do not run `make qa-smoke` or `make qa-full` in this wave.

---

# 9. Coding-agent Definition of Done

Implementation work may stop only when:

1. every `PARTIAL` / `TODO` item in this backlog is either completed or explicitly documented as blocked,
2. runtime integration has been verified for helpers that previously existed only in isolation,
3. no protected P0 guardrail regressed,
4. targeted regression tests pass,
5. typecheck/lint pass as appropriate,
6. repository pytest is run once at the end if environment permits,
7. `git diff --check` passes,
8. the agent reports exact task IDs completed/remaining with changed files and test evidence,
9. **the agent has not automatically run `make qa-smoke`, `make qa-full`, or the 386 benchmark.**

Then STOP and return control to the maintainer.

---

# 10. Maintainer final acceptance workflow

After reviewing the completed implementation:

```text
review git diff
        ↓
make qa-smoke
        ↓
if P0 clean
        ↓
make qa-full
        ↓
5 canonical Q&A transcripts
+ technical artifacts
+ unified summary
        ↓
manual grade 386
        ↓
update GA2_VERIFICATION_EVIDENCE.md
        ↓
only then mark GA2 complete
```

Do not run another expensive 386 benchmark while implementation tasks are still changing. Benchmark the final candidate revision.

---

# 11. Final maintainer acceptance gates

## P0 invariants

- [ ] 0 hidden-reasoning leakage.
- [ ] 0 explicit unknown-target -> localhost fallback.
- [ ] 0 hard-source violation.
- [ ] 0 unsupported current claim when external evidence is unavailable.
- [ ] 0 unsupported current/version/date/price/identity claim from URL evidence.
- [ ] 0 hidden prompt/secret/private-key disclosure.
- [ ] 0 executed infrastructure mutation.
- [ ] SSRF/private-IP/redirect/DNS-rebinding protections remain intact.

## Behavior gates

- [ ] `make qa-smoke` passes.
- [ ] Full 386 weighted score >= 95%.
- [ ] Every individual suite weighted score >= 90%.
- [ ] Overall FAIL rate <= 3%.
- [ ] Current/external-decision correctness >= 98%.
- [ ] Explicit-target safety correctness = 100%.
- [ ] Hard source-constraint correctness = 100%.
- [ ] External grounding correctness >= 98%.
- [ ] No critical language corruption.
- [ ] No general/meta request enters environment inspection solely because of an infrastructure noun.

## Engineering gates

- [ ] typecheck passes.
- [ ] `ruff check .` passes.
- [ ] full repository pytest passes.
- [ ] `git diff --check` passes.
- [ ] `qa-full` actually runs `run_tests_v2 + baseline + acceptance + 386` under one canonical run.
- [ ] five canonical transcripts exist in the same run directory.
- [ ] unified report exists.
- [ ] runtime manifest exists.
- [ ] final `docs/project/GA2_VERIFICATION_EVIDENCE.md` points to the final tested revision/run.

---

# 12. Final instruction to the coding agent

Work this as an implementation backlog, not as an autonomous release loop.

```text
DO:
- read the repository before each remaining task
- finish only PARTIAL/TODO items
- verify runtime integration, not helper existence
- preserve all DONE/P0 guardrails
- add deterministic regression tests
- make qa-smoke/qa-full correct
- report exact task IDs and evidence

DO NOT:
- trust previous model self-reported DONE statuses over source
- run the 386 benchmark automatically
- run make qa-smoke automatically
- run make qa-full automatically
- consume model/runtime quota in fix -> benchmark loops
- declare GA2 accepted without maintainer-run final grading
```

The file itself is the continuation source of truth even if the model context is compacted or truncated.
