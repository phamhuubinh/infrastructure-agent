# Manual QA runners

These scripts exercise Orion against configured model servers and infrastructure targets. They are not part of the unit test suite and may make real outbound requests.

Run them from the repository root:

```bash
python3 scripts/qa/run_tests.py
python3 scripts/qa/run_tests_v2.py
python3 scripts/qa/run_acceptance.py
```

Generated JSON/Markdown reports and runtime-evidence pointers are written to `artifacts/qa/`, which is intentionally excluded from version control.
