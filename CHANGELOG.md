# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Secrets moved from source code to gitignored config/secrets.local.json
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

## [Unreleased]