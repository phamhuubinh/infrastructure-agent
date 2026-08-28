# Orion live QA

`make qa-smoke` and `make qa-full` are manual-only live commands: they are not dependencies of
tests, lint, acceptance, CI, installation, builds, or Orion startup. They launch an isolated
loopback Orion API with a temporary SQLite database and exercise the current HTTP session API.
They never use Docker or the legacy `/api/query` endpoint. The runner reads an active local model
profile without modifying it, or uses `ORION_QA_MODEL_BASE_URL`, `ORION_QA_MODEL_ID`, and
optionally `ORION_QA_MODEL_API_KEY`.

Reports are written under `artifacts/qa/`. Linux, Grafana, and Zabbix cases are explicitly
reported as `SKIP` unless a safe QA capability is configured; they never target production files.
