# 08 - Project State
> Source of truth for "what actually exists." If this file and any other doc disagree, this file wins (see `00_BOOTSTRAP.md`). Update this file whenever status changes — do not let it drift from reality (`07_DEVELOPMENT_RULES.md`, rule 25).
## Phase
**Local MVP.** Single-user, single-machine, no network exposure beyond outbound calls to targets/Grafana/Zabbix/LLM APIs. The platform direction in `03_PLATFORM_ARCHITECTURE.md` / `04_ROADMAP.md` has not started (WP1 has not begun — no public VM yet).
## Implemented
- Deterministic pipeline: Intent Resolution → Target Resolution → Evidence Planning → Execution Graph → Execution Runtime (`src/pipeline/*`).
- `KnowledgeTool` as the single dispatch entry point to Child Tools (`src/tool/knowledge_tool.py`).
- Child Tools: `LinuxTool` (SSH execution via `execution_backend.py`), `GrafanaTool`, `ZabbixTool`.
- Local target registry backed by a JSON file (`src/tool/target_registry.py`, `target_store.py`).
- Assessment layer: `LLMAssessmentAdapter` (real) and `MockAssessmentAdapter` (offline/dev), behind the `AssessmentModelAdapter` interface (`src/model/*`).
- CLI entry point with local mode and `--web` mode (`src/cli.py`).
- Web UI (TanStack Start / React) for local dev use (`ui/`), talking to the local backend started by `--web`.
## Not implemented (do not assume otherwise)
- **Automated tests.** There is no test directory and no test files in the repository. Any prior documentation claiming "Testing: Implemented" was inaccurate and has been corrected here.
- **Benchmark framework.** No benchmark runner exists. `.gitignore` still references a `.benchmark_history.json` pattern from an earlier iteration, but no benchmark code currently exists in the repository.
- Database — no PostgreSQL, no persistence layer beyond the local targets JSON file.
- Authentication / accounts.
- Remote hosting, HTTPS, reverse proxy, Docker Compose deployment.
- Dify integration, RAG, Document Service.
- Desktop App.
- Internet Tool (planned for WP4, opt-in-only when built — see `04_ROADMAP.md`).
## Known issues / open items being tracked
- **Dependency declaration**: `pyproject.toml` currently lists `dependencies = []` while the codebase has real imports beyond the standard library — needs to be reconciled (rule 15, `07_DEVELOPMENT_RULES.md`).
- **Credential handling**: tool defaults for Grafana/Zabbix must not hardcode tokens (rule 16). The mechanism for how credentials are supplied locally (env var / gitignored config / OS credential store) should be recorded in `09_ARCHITECTURE_DECISIONS.md` once settled, and this section updated to say which one is actually implemented.
- **SSH host key checking** is currently disabled by design for the local trusted-network use case — this is an intentional trade-off, recorded in `09_ARCHITECTURE_DECISIONS.md`, not an oversight.
- Some structural directories (`src/knowledge/`, `src/schema/`, `src/runtime/`) exist as empty scaffolding with no files. Treat as reserved-but-unused; do not build against them without confirming intent first.
## Next milestones
1. Reconcile dependency declarations and credential handling (housekeeping, no roadmap dependency).
2. Add a minimal automated test suite covering the pipeline's deterministic core (target registry, execution backend, KnowledgeTool dispatch) before further pipeline changes land.
3. WP1 (`04_ROADMAP.md`) begins once public VM access is available — not before.
