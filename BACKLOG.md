# Orion Backlog

Generated: 2026-07-17
Source: Phase 0 exhaustive discovery — all 10 docs/ai/ files verified against source code.

---

## Priority Legend
- **P0**: Must-do — missing tests, blocking coverage gaps, broken features
- **P1**: Important — stale docs, silent exception swallowing, dependency issues, missing features
- **P2**: Quality — minor refactors, cleanup, documentation improvements

---

## P0 Tasks (6 remaining)

### T-003 — Write unit tests for src/pipeline/evidence_merge.py, evidence_package.py, evidence_completeness.py
- **Source:** docs/ai/08_PROJECT_STATE.md, backlog
- **DoD:** Dedicated test file exists, all tests pass.

### T-004 — Write unit tests for src/pipeline/execution_engine.py — full pipeline integration
- **Source:** docs/ai/08_PROJECT_STATE.md, backlog
- **DoD:** Test file exists covering execute() happy path and edge cases, all tests pass.

### T-005 — Write unit tests for src/pipeline/assessment_adapter.py
- **Source:** docs/ai/08_PROJECT_STATE.md, backlog
- **DoD:** Dedicated test file exists, all tests pass.

### T-006 — Write unit tests for src/pipeline/deterministic_responder.py
- **Source:** docs/ai/08_PROJECT_STATE.md, backlog
- **DoD:** Test file exists covering all response paths, all tests pass.

### T-007 — Write unit tests for src/tool/execution_backend.py
- **Source:** docs/ai/08_PROJECT_STATE.md, backlog
- **DoD:** Test file exists covering LocalExecutionBackend and SSHExecutionBackend, all tests pass.

### T-008 — Write unit tests for src/model/mock_assessment_adapter.py
- **Source:** docs/ai/08_PROJECT_STATE.md, backlog
- **DoD:** Test file exists, all tests pass.

---

## P1 Tasks (11)

| ID | Category | Description | Source |
|----|----------|-------------|--------|
| T-009 | code-quality | Fix PTH118 os.path.join() — replace with Path / operator (17 occurrences) | Ruff |
| T-010 | observability | Fix silent exception swallowing — add logging before pass in 4 files | Phase 0 |
| T-011 | documentation | Fix 08_PROJECT_STATE.md — benchmark runner now exists | docs/ai/08 |
| T-012 | documentation | Fix 02_CURRENT_ARCHITECTURE.md — src/cli.py -> src/cli/main.py | docs/ai/02 |
| T-013 | code-quality | Fix I001 unsorted imports across all src/ files | Ruff |
| T-014 | code-quality | Fix F841 unused variables in linux_tool.py, grafana_tool.py | Ruff |
| T-015 | code-quality | Fix TRY003/EM101/EM102 exception style rules | Ruff |
| T-016 | code-quality | Fix Q000 single quotes vs double quotes across src/ | Ruff |
| T-024 | enhancement | Implement early completion in ExecutionRuntime (05_EXECUTION_PIPELINE.md line 60) | docs/ai/05 |
| T-025 | metadata | Add missing capability metadata fields (description, supported targets, parameters, estimated cost) | docs/ai/06 |
| T-026 | dependencies | Fix pyproject.toml — fastapi/uvicorn/pydantic are runtime deps, remove unused requests/numpy | docs/ai/07 rule 15 |
| T-027 | documentation | Fix 08_PROJECT_STATE.md claim about RAGTool — it exists at src/tool/RAGTool/ | docs/ai/08 |
| T-028 | documentation | Fix 02_CURRENT_ARCHITECTURE.md line 59-61 — tests and benchmark exist | docs/ai/02 |

---

## P2 Tasks (12)

| ID | Category | Description | Source |
|----|----------|-------------|--------|
| T-017 | documentation | Fix stale doc refs in code — evidence_planner.py:9, capability_library.py:6 | Code comments |
| T-018 | ci | Create .github/workflows/ci.yml | CHANGELOG |
| T-019 | security | Fix tools.json/servers.json gitignore inconsistency | .gitignore |
| T-021 | cleanup | Remove ui/AGENTS.md and ui/.lovable/ | 08_PROJECT_STATE.md |
| T-022 | refactor | Initialize _INTENT_PROMPTS at module level in prompt_builder_v2.py | Phase 0 |
| T-023 | documentation | Document .workflow directory in README | Phase 0 |
| T-029 | enhancement | Add intra-execution caching to avoid duplicate infra access | docs/ai/06 |
| T-030 | cleanup | Update .clinerules to follow reading order from 00_BOOTSTRAP.md | docs/ai/00 |
| T-020 | dependencies | Remove unused numpy/requests from pyproject.toml | Phase 0 |

---

## Summary
- **P0: 6 remaining** (T-003 to T-008) — all testing coverage
- **P1: 13** (T-009 to T-016 + T-024 to T-028) — code quality, docs, dep fix
- **P2: 9** (T-017 to T-023 + T-029, T-030) — cleanup, refactor, CI
- **Total remaining: 28**
- **Completed: 2** (T-001, T-002)
