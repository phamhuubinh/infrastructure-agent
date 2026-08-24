# Changelog

## [Unreleased]

### Added

- Canonical target architecture/ADR documentation.
- `docs/development/IMPLEMENTATION_GAPS.md`, the current defect/convergence ledger.
- ADR-0009: protected system/developer/internal instructions are not user-retrievable and use canonical `REFUSE`.

### Changed

- Configured Web/CLI Chat construction uses the canonical model-driven runtime.
- Documentation now distinguishes target architecture, implementation truth, and known defects.
- Agent-runtime docs define stage-specific legality and post-generation harness validation.
- Evidence docs distinguish dispatched attempts from successful observations and require objective final-claim checks.
- Model docs define configured identity grounding and explicit health states.
- Security docs distinguish root internal RAG from the currently unhardened standalone development stack.
- Testing docs distinguish full local unit/static validation from explicit live Docker/model/GA2 gates.
- QA docs no longer describe `budget.actions_used` as proof of successful tool execution.

### Removed

- Superseded deterministic/semantic routing from configured primary Chat construction and no-caller compatibility contracts from that refactor scope.

## [0.1.0] — 2026-07-22

Historical initial release: deterministic infrastructure investigation stack, tool integrations, CLI/Web UI, RAG service, persistence, Docker deployment, API auth, benchmark/CI/security tooling.
