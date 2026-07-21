# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Comprehensive test suite: 764 tests across pipeline, tools, model, backend, agent, benchmark

### Security
- Secrets moved from source code to gitignored config/secrets.local.json
- InternetTool SSRF protection (private IP block + DNS resolution guard)
- API auth via optional API key middleware
- Security scanning in CI: Bandit (static analysis), Safety (dependency check), pip-audit (package CVEs)
- `make security-scan` target, integrated into `make ci`
- New `[security]` optional dependency group in pyproject.toml
- Security documentation updated in SECURITY.md
