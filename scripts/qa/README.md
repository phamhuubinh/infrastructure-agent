# Manual QA runners

These scripts exercise Orion against configured model servers and infrastructure targets. They are
not part of the ordinary unit-test suite and may start Docker or make real outbound requests.

Run them from the repository root.

```bash
# Canonical GA2 smoke gate
make qa-smoke
# equivalent:
python3 scripts/qa/ga2_runner.py --mode smoke --fail-fast

# Unified/full QA
make qa-full
# equivalent:
python3 scripts/qa/unified_qa.py
```

Additional/manual runners remain available for focused historical suites:

```bash
python3 scripts/qa/run_tests.py
python3 scripts/qa/run_tests_v2.py
python3 scripts/qa/run_acceptance.py
```

Generated JSON/Markdown reports and runtime-evidence pointers are written to `artifacts/qa/`, which
is intentionally excluded from version control.

## GA2 runtime contract

`ga2_runner.py` is an HTTP black-box runner: it talks to the Docker API that a user would receive
instead of importing the agent runtime directly. The configured application under test must be the
canonical agent path.

It reports two independent automated gate families:

- **Safety P0** — leakage, secret disclosure, unknown-target execution, source-constraint loss, and
  failed/empty API behavior.
- **Runtime viability** — whether representative cases actually exercised usable model/tool runtime
  behavior instead of collapsing into a systemic provider/runtime failure.

`summary.json`, `summary.md`, and the unified aggregate report retain both families beside manual
behavioral grading. `PENDING_MANUAL_REVIEW` never overrides a failed P0 or viability gate.

## Important compatibility note

At baseline `259f85b`, `ga2_runner.py` still contains compatibility-named viability fields and
counters such as `semantic_loop` and `planner_failure_*`. Those names are **not architecture
authority** and must not be used as a reason to restore the removed deterministic/semantic planner
stack.

If a fresh canonical run fails `Runtime viability`, inspect the generated report and the runner ↔
public trace contract first. Fix the first real failure. Do not treat later cascade failures as
independent architecture problems and do not resurrect legacy routing merely to satisfy an old
metric name.

## Before a live run

Confirm the Git revision and working tree that the runtime will attest, then ensure the intended
model/targets are configured. GA2 records the git SHA, dirty-worktree flag, API image/container
identity, and selected non-secret feature flags in its runtime manifest.

The runner can start the QA Compose stack itself. Use its `--no-start` option only when intentionally
testing an already-running compatible API.
