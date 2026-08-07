# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed
- Unused Dify API/Web services, their dedicated Redis service, reverse-proxy route, and environment wiring. Orion continues to use its first-party chat routing and RAG service.
- Autonomous development supervisor, orchestrator state/transcripts, generated task logs, and related repository instructions. GitHub Actions CI remains unchanged.
- Committed Python build metadata, stale machine-specific QA reports, benchmark history, and a duplicate BM25 edge-case script.

### Changed
- Moved project plans to `docs/project/`, OpenAPI schema to `docs/api/`, and manual QA runners to `scripts/qa/`; QA output now goes to ignored `artifacts/qa/`.
- Restored foreground `orion web` lifecycle semantics for Docker installs: it follows only current API/UI logs without replaying historical proxy noise and stops Web services on `Ctrl+C`, while `orion log` follows the complete stack without stopping it.
- Made uninstall clean model/session/RAG volumes and private runtime state by default, with a separate interactive choice for removing shared Grafana/Zabbix credentials.

### Release verification — Deterministic Reasoning v1

Before promoting a DR1 release candidate, record the candidate commit and configuration hash, then
complete all of the following. A successful fixture run proves the CI gate is wired correctly; it is
not a substitute for the meaningful model/config baseline.

- [ ] The candidate changes are grouped into reviewable logical commits; each completed DR1 task
  has its scoped implementation/doc changes and recorded test evidence in
  `docs/project/DETERMINISTIC_REASONING_BACKLOG.md`. Where an earlier historical commit delivered
  a batch of task IDs, link each ID to the relevant files and verification evidence in that batch.
- [ ] Required CI jobs are green, including the Python, UI, RAG, container/smoke, and
  `acceptance-gates` jobs.
- [ ] The P0 offline suite passes: `tests/qa/test_golden_schema.py`,
  `tests/qa/test_transcript_regression.py`, `tests/qa/test_acceptance_scoring.py`, and
  `tests/security/`.
- [ ] Run `python3 scripts/qa/run_acceptance.py --report
  tests/data/qa_cases/acceptance_fixture.json --output-dir artifacts/qa` and retain
  `artifacts/qa/acceptance_gates.json` plus `artifacts/qa/acceptance_gates.md` with PASS status.
- [ ] With the configured assessment model healthy, run `python3 scripts/qa/run_baseline.py
  --server <server> --output-dir benchmark_results`; retain the timestamped
  `benchmark_results/baseline_<timestamp>.json` and `.md` files. Their metadata records the Git
  commit, config hash, provider/model, and capture time. A `smoke_<timestamp>` report is not a
  release baseline.
- [ ] Compare the meaningful baseline to the approved prior baseline; all mandatory gates in
  `docs/project/DETERMINISTIC_REASONING_BACKLOG.md` section 14 pass, including no unsafe receipt,
  no empty success response, and the accepted accuracy/performance budget.
- [ ] Review `git diff --check` and `git status --short`; publish only after the release reviewer
  has linked the CI run and retained artifacts to the release record.

Completing this checklist authorizes a release decision; it does not by itself change Orion's local,
single-user deployment scope.

## [0.1.0] — 2026-07-22

### Added
- Initial infrastructure investigation platform
- Deterministic pipeline: Intent Resolution → Target Resolution → Evidence Planning → Capability Resolution → Execution Planning → Execution Graph → Execution Runtime
- KnowledgeTool as single dispatch entry point for Child Tools
- Child Tools: LinuxTool (SSH), GrafanaTool, ZabbixTool, InternetTool (SSRF-protected HTTP fetch), KnowledgeBaseTool (RAG service proxy)
- Local target registry backed by JSON file
- Assessment layer: LLMAssessmentAdapter and MockAssessmentAdapter
- CLI entry point with local and web modes
- Web UI (TanStack Start / React) with step-by-step pipeline visualization
- Benchmark framework with scoring, reporting, regression detection
- Session management with conversation persistence (JSON + optional PostgreSQL)
- DeterministicResponder for simple responses without LLM
- Fuzzy target name matching
- Ctrl+C cancel support
- RAG microservice with embedding, vector store, OCR, chunking, GraphRAG
- Docker Compose deployment: nginx, FastAPI, React UI, PostgreSQL, Dify, Redis, RAG service
- Desktop App (Electron wrapper)
- API authentication (optional `ORION_API_KEY` middleware)
- Document upload/list/delete API endpoints
- CI with multi-Python-version testing, Docker build, smoke tests, security scanning
- Comprehensive test suite: 855 tests across pipeline, tools, model, backend, agent, benchmark

### Security
- Secrets moved from source code to an external credentials file (now standardized at `/etc/orion/tool-credentials.json`)
- InternetTool SSRF protection (private IP block + DNS resolution guard)
- API auth via optional API key middleware
- Security scanning in CI: Bandit (static analysis), Safety (dependency check), pip-audit (package CVEs)
- `make security-scan` target, integrated into `make ci`
- New `[security]` optional dependency group in pyproject.toml
- Security documentation updated in SECURITY.md
- SSH Host Key Checking now configurable per target in targets.json

### Fixed
- Logger crash on read-only filesystem — fallback to stderr
- Platform-specific issues in Linux tool execution
- Various lint fixes (ruff E, F, I, UP, B rules) across full codebase
- Packaging: `src` module discovery, benchmark output path, misplaced files

### Changed
- Split large tool files into packages:
  - Linux (1701 lines): divided into `linux/` subpackage
  - Zabbix (991 lines): divided into `zabbix/` subpackage
  - Grafana (824 lines): divided into `grafana/` subpackage
- DRY refactoring: `ExecutionBackend` factored into shared module
- Evidence serialization optimized for frontend — never sends full raw data
- Safe data serialization improved — handles nested dicts/lists, circular refs
- Error messages sanitized — no internal paths or source info leaked
- Sensitive info masked in logs — passwords, tokens, API keys
- Conversation summary threshold now configurable via `ORION_CONVERSATION_THRESHOLD` env var
- Frontend dev port now configurable via `ORION_FRONTEND_PORT` env var
- Backlog format standardized with auto-generation script

### Removed
- Dead code and unused imports across entire project
- Committed `tools.json` artifact — now generated from capability library
- Plaintext secrets from repository (moved to gitignored config file)

### Documentation
- All docs synchronized with current codebase
- ADR-0002 (LLM assessment only) created
- ADR-0003 (KnowledgeTool single entry point) created
- ADR-0004 (stateless state management) created
- Architecture decisions cross-referenced
- Standardized documentation structure

### Testing
- 855 tests passing, 4 skipped
- Thread safety tests for ConversationStore, ExecutionRuntime, Tool execution
- Regression tests for previously fixed runtime bugs
- Backend API test coverage increased
- UI test stage added to CI
