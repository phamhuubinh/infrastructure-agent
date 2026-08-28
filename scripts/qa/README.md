# Orion live QA

`make qa-smoke` and `make qa-full` are manual-only live commands: they are not dependencies of
tests, lint, acceptance, CI, installation, builds, or Orion startup. They launch isolated
loopback Orion APIs with temporary SQLite databases and exercise the current HTTP session API.
They never use Docker or the legacy `/api/query` endpoint. The runner reads an active local model
profile without modifying it, or uses `ORION_QA_MODEL_BASE_URL`, `ORION_QA_MODEL_ID`, and
optionally `ORION_QA_MODEL_API_KEY`.

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

Reports are written under `artifacts/qa/`. Linux, Grafana, and Zabbix cases are explicitly
reported as `SKIP` unless a safe QA capability is configured; they never target production files.
Full reports distinguish structured results from historical suite/prompt-turn results and retain
only bounded safe diagnostics, never raw prompts, answers, tool payloads, or timelines.
