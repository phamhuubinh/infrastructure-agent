# GA2 verification evidence

> **Status:** PENDING_MANUAL_REVIEW

## Latest canonical runtime run

- Mode: `smoke`
- Run artifact: `artifacts/qa/runs/20260808_095621_3651bb2abc91`
- Created: `2026-08-08T09:56:20.718699+00:00`
- Git SHA: `3651bb2abc911bc62616b14cf84c192b4662be88`
- Dirty worktree: `True`
- Cases completed: `37`
- Automated P0 gate: **PASS** (0 violation(s))

## Gate interpretation

A clean automated P0 gate confirms the runtime checks for reasoning leakage, secret disclosure, unknown-target execution and typed source-constraint loss. It does **not** replace the documented manual behavioral grade for all 386 cases.

## GA2 closure checks

- Run `make qa-full` and retain its fresh 386-case artifact.
- Complete manual PASS/PARTIAL/FAIL grading; the score must meet the GA2 thresholds.
- Complete `make typecheck`, `ruff check .`, full repository `pytest`, and `git diff --check`.
