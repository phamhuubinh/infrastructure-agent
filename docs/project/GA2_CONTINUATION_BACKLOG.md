# Orion — GA2 Continuation Backlog (Local-Agent Manifest)

> **Status:** Active
> **Checkpoint audited:** `081efc393dc2`
> **Current reconciliation:** post-checkpoint implementation wave for `A06/A09/A10/C10/D07/D08/E02` is accepted as DONE; targeted reconciliation tests: `35 passed`.
> **Purpose:** keep the continuation state authoritative **without forcing a local model to read a 38 KB backlog**.

## LOCAL MODEL: READ THIS FIRST, THEN STOP READING THIS FILE

Work **one task per fresh Cline session**. After selecting a task from the active table below, open **only that task packet** under `docs/project/ga2_tasks/`.

Do **not** read every task packet. Do **not** read an older/full GA2 backlog unless the maintainer explicitly asks.

### Context budget contract

1. Target working context: **<= 35K tokens**; do not intentionally fill the 64K window.
2. For source files over ~300 lines, **do not use whole-file read** unless the task packet explicitly permits it.
3. Locate symbols with `rg -n`, then inspect bounded ranges with `sed -n 'START,ENDp'`.
4. If extra context is required: state what is missing -> `rg` the exact symbol/reference -> read at most about +/-80 lines around it.
5. Never scan `docs/**`, `src/**`, or `tests/**` recursively as task bootstrap.
6. Distinguish **definition lines** from **call sites**. Never claim a test proves more than its explicit assertions.
7. If a named symbol/path is absent, report that; **do not invent a replacement**.
8. Edit only files in the packet's `EDIT SCOPE`. To touch another file, first show the concrete import/call/reference that requires it.
9. Run only the packet's targeted tests during implementation. Do not run `qa-smoke`, `qa-full`, or the 386 runtime suite.
10. Before DONE: targeted tests pass, changed-file lint/typecheck where applicable, `git diff --check`, inspect the final diff.
11. **STOP after one task.** Do not opportunistically repair neighboring PARTIAL tasks.
12. If the Cline context meter approaches ~45K before tests/final review, stop and start a fresh session rather than carrying a long speculative history.

## Current state

| Epic | DONE | PARTIAL | TODO |
|---|---:|---:|---:|
| A | 11 | 0 | 0 |
| B | 6 | 0 | 0 |
| C | 9 | 1 | 0 |
| D | 9 | 0 | 0 |
| E | 6 | 2 | 0 |
| F | 6 | 4 | 0 |
| G | 8 | 1 | 0 |
| H | 2 | 8 | 2 |
| **TOTAL** | **57** | **16** | **2** |

### DONE IDs — preserve, do not reimplement

```text
A01-A11
B01-B06
C01-C06, C08-C10
D01-D09
E01-E03, E05-E07
F01-F03, F06, F08-F09
G01-G07, G09
H01, H09
```

## Active tasks

| Order | Task | Pri | Status | Dependency | Packet |
|---:|---|---|---|---|---|
| 1 | GA2-C07 | P1 | PARTIAL | — | `ga2_tasks/GA2-C07.md` |
| 2 | GA2-F07 | P1 | PARTIAL | C07 | `ga2_tasks/GA2-F07.md` |
| 3 | GA2-E04 | P1 | PARTIAL | — | `ga2_tasks/GA2-E04.md` |
| 4 | GA2-E08 | P1 | PARTIAL | — | `ga2_tasks/GA2-E08.md` |
| 5 | GA2-F04 | P0 | PARTIAL | — | `ga2_tasks/GA2-F04.md` |
| 6 | GA2-F05 | P0 | PARTIAL | F04 | `ga2_tasks/GA2-F05.md` |
| 7 | GA2-F10 | P1 | PARTIAL | — | `ga2_tasks/GA2-F10.md` |
| 8 | GA2-G08 | P1 | PARTIAL | — | `ga2_tasks/GA2-G08.md` |
| 9 | GA2-H02 | P1 | PARTIAL | — | `ga2_tasks/GA2-H02.md` |
| 10 | GA2-H04 | P2 | PARTIAL | — | `ga2_tasks/GA2-H04.md` |
| 11 | GA2-H05 | P2 | TODO | — | `ga2_tasks/GA2-H05.md` |
| 12 | GA2-H03 | P1 | PARTIAL | H02/H04/H05 behavior must remain distinct | `ga2_tasks/GA2-H03.md` |
| 13 | GA2-H06 | P2 | PARTIAL | H03 generation strategy | `ga2_tasks/GA2-H06.md` |
| 14 | GA2-H07 | P2 | PARTIAL | H06 | `ga2_tasks/GA2-H07.md` |
| 15 | GA2-H08 | P2 | PARTIAL | H06 | `ga2_tasks/GA2-H08.md` |
| 16 | GA2-H12 | P2 | PARTIAL | — | `ga2_tasks/GA2-H12.md` |
| 17 | GA2-H10 | P2 | PARTIAL | D08 DONE; preferably reuse H12 final boundary | `ga2_tasks/GA2-H10.md` |
| 18 | GA2-H11 | P2 | TODO | last | `ga2_tasks/GA2-H11.md` |

The order is a safe continuation order, not permission to do multiple tasks in one session.

## Protected invariants

Do not regress:

- unresolved explicit target => **zero** environment execution; never localhost fallback;
- hard source restriction never silently becomes `ANY`;
- hidden reasoning/system prompts/credentials remain sanitized or refused;
- SSRF/private/loopback/link-local/DNS-rebinding/redirect controls remain fail-closed;
- fetch success != extracted content != relevant evidence != sufficient evidence;
- missing evidence remains UNKNOWN/unavailable, never model-memory certainty;
- Orion remains read-only; generated mutating commands are content, not execution receipts;
- frozen full acceptance baseline remains exactly **386 cases**.

## Status update rule

A coding agent may change a task from PARTIAL/TODO to DONE only when the packet acceptance contract and targeted tests are satisfied. Update only:

1. the one row in this manifest,
2. aggregate counts,
3. that packet's `STATUS` and `IMPLEMENTATION EVIDENCE`.

Do not rewrite DONE history or infer whole-GA2 completion.

## Maintainer-only release gate

After all implementation packets are DONE, the coding agent stops. The maintainer separately performs final `qa-smoke`, final 386 `qa-full`, manual grading, and release acceptance. Unit tests or HTTP 200 alone do not constitute GA2 release acceptance.
