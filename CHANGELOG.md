# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial infrastructure investigation platform
- Deterministic pipeline: Intent Resolution → Target Resolution → Evidence Planning → Execution Graph → Execution Runtime
- KnowledgeTool as single dispatch entry point for Child Tools
- Child Tools: LinuxTool (SSH), GrafanaTool, ZabbixTool
- Local target registry backed by JSON file
- Assessment layer: LLMAssessmentAdapter and MockAssessmentAdapter
- CLI entry point with local and web modes
- Web UI (TanStack Start / React)
- Benchmark framework with scoring and reporting
- Session management with conversation persistence
- DeterministicResponder for simple responses without LLM

### Security
- Secrets moved from source code to gitignored config/secrets.local.json
- See README.md for credential management

### Added
- Security scanning in CI: Bandit (static analysis), Safety (dependency check), pip-audit (package CVEs)
- `make security-scan` target, integrated into `make ci`
- New `[security]` optional dependency group in pyproject.toml
