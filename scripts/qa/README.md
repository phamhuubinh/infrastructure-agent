# Manual QA runners

These scripts exercise Orion against configured model servers and infrastructure targets. They are not part of the unit test suite and may make real outbound requests.

Run them from the repository root:

```bash
python3 scripts/qa/run_tests.py
python3 scripts/qa/run_tests_v2.py
python3 scripts/qa/run_acceptance.py
```

Generated JSON/Markdown reports and runtime-evidence pointers are written to `artifacts/qa/`, which is intentionally excluded from version control.

## GA2 runtime gates

`ga2_runner.py` reports two independent automated gate families:

- **Safety P0** checks leakage, secret disclosure, unknown-target execution,
  and source-constraint loss.
- **Runtime viability** checks that the representative run did not collapse
  into planner/provider failure or technical fallback, and that required
  model and tool paths executed successfully.

`summary.json`, `summary.md`, and the unified aggregate report retain both
families beside the manual behavioral grading status. `PENDING_MANUAL_REVIEW`
never overrides a failed P0 or viability gate; either failure exits nonzero and
makes the run technically invalid for behavioral acceptance.
