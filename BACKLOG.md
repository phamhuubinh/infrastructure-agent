# Orion Backlog

Generated: 2026-07-17
Source: Phase 0 exhaustive discovery — all docs, code, ADRs, TODOs, comments.

---

## Priority Legend
- **P0**: Must-do — missing tests, blocking coverage gaps, broken features
- **P1**: Important — stale docs misrepresenting state, silent exception swallowing, incomplete CI
- **P2**: Quality — missing reference docs, stale doc references, unused deps, minor inconsistencies

---

## P0 Tasks

### T-001 — Write unit tests for src/agent/conversation_store.py
- **Source:** Backlog item #1, docs/ai/08_PROJECT_STATE.md
- **Description:** Test file exists at tests/agent/test_conversation_store.py but is newly created. Verify all 33 tests pass, fix any failures, and ensure coverage is adequate.
- **Related files:** src/agent/conversation_store.py, tests/agent/test_conversation_store.py
- **DoD:** All tests pass, no regressions.

### T-002 — Write unit tests for src/agent/runtime_factory.py
- **Source:** Backlog item #2, docs/ai/08_PROJECT_STATE.md
- **Description:** Test file exists at tests/agent/test_runtime_factory.py but is newly created. Verify all tests pass, fix failures, confirm coverage.
- **Related files:** src/agent/runtime_factory.py, tests/agent/test_runtime_factory.py
- **DoD:** All tests pass, no regressions.

### T-003 — Write unit tests for src/pipeline/evidence_merge.py, evidence_package.py, evidence_completeness.py
- **Source:** Backlog item #3
- **Description:** These modules are tested only indirectly through integration tests. Write dedicated unit tests.
- **Related files:** src/pipeline/evidence_merge.py, evidence_package.py, evidence_completeness.py
- **DoD:** Dedicated test file exists, all tests pass.

### T-004 — Write unit tests for src/pipeline/execution_engine.py — full pipeline integration
- **Source:** Backlog item #4
- **Description:** ExecutionEngine orchestrates the full pipeline but has no dedicated test file.
- **Related files:** src/pipeline/execution_engine.py
- **DoD:** Test file exists covering execute() happy path and edge cases, all tests pass.

### T-005 — Write unit tests for src/pipeline/assessment_adapter.py
- **Source:** Backlog item #5
- **Description:** AssessmentAdapter converts InvestigationRequest to AssessmentRequest. Only tested through AssessmentRequest tests.
- **Related files:** src/pipeline/assessment_adapter.py
- **DoD:** Dedicated test file exists, all tests pass.

### T-006 — Write unit tests for src/pipeline/deterministic_responder.py
- **Source:** Backlog item #6
- **Description:** DeterministicResponder handles zombie processes and service status without LLM. No dedicated tests.
- **Related files:** src/pipeline/deterministic_responder.py
- **DoD:** Test file exists covering all response paths, all tests pass.

### T-007 — Write unit tests for src/tool/execution_backend.py (LocalExecutionBackend, SSHExecutionBackend)
- **Source:** Backlog item #7
- **Description:** Execution backends are tested inline but have no dedicated test file.
- **Related files:** src/tool/execution_backend.py
- **DoD:** Test file exists covering both backends, all tests pass.

### T-008 — Write unit tests for src/model/mock_assessment_adapter.py
- **Source:** Backlog item #8
- **Description:** MockAssessmentAdapter has no dedicated tests.
- **Related files:** src/model/mock_assessment_adapter.py
- **DoD:** Test file exists, all tests pass.

---

## P1 Tasks

### T-009 — Fix all PTH118 os.path.join() calls — replace with Path / operator across src/
- **Source:** Ruff lint output, backlog
- **Description:** 17 occurrences of os.path.join() that should use Path(/ operator per modern Python standards.
- **Related files:** src/agent/conversation_store.py, src/backend/app.py, src/cli/main.py, src/shared/logger.py
- **DoD:** Zero PTH118 violations in ruff check.

### T-010 — Fix silent exception swallowing (add logging before pass)
- **Source:** Phase 0 discovery — `src/shared/logger.py`, `src/backend/app.py`, `src/agent/deterministic_agent.py`, `src/agent/conversation_store.py`
- **Description:** Multiple `except Exception: pass` blocks silently swallow errors in critical paths. Add at minimum debug-level logging.
- **Related files:** logger.py, app.py, deterministic_agent.py, conversation_store.py
- **DoD:** No silent `except.*pass` without at least a log call.

### T-011 — Fix stale project state doc
- **Source:** docs/ai/08_PROJECT_STATE.md
- **Description:** Line 53 falsely claims "no benchmark runner exists yet" — benchmark/ directory has full runner.
- **DoD:** 08_PROJECT_STATE.md accurately reflects benchmark runner existence.

### T-012 — Fix stale file path in 02_CURRENT_ARCHITECTURE.md
- **Source:** docs/ai/02_CURRENT_ARCHITECTURE.md line 4
- **Description:** References `src/cli.py` but actual file is `src/cli/main.py`.
- **DoD:** Architecture doc uses correct path.

### T-013 — Fix I001 unsorted imports across src/ files
- **Source:** Ruff output (132 fixable)
- **Description:** Multiple files have unsorted/unformatted import blocks.
- **Related files:** knowledge_tool.py, linux_tool.py, target_store.py, zabbix_tool.py, grafana_tool.py
- **DoD:** Zero I001 violations.

### T-014 — Fix F841 unused variables in linux_tool.py and grafana_tool.py
- **Source:** Ruff output
- **Description:** `options`, `plugin_options`, `p_clean` variables assigned but never used.
- **DoD:** Zero F841 violations in src/.

### T-015 — Fix TRY003/EM101/EM102 exception style rules across src/
- **Source:** Ruff output
- **Description:** Exception messages should not use f-string literals or string literals directly; assign to variable first.
- **DoD:** Zero TRY003/EM101/EM102 violations in src/.

### T-016 — Fix Q000 single quotes vs double quotes across src/
- **Source:** Ruff output
- **Description:** Mixed quote style; project should use double quotes consistently.
- **DoD:** Zero Q000 violations.

---

## P2 Tasks

### T-017 — Fix stale doc references in source code
- **Source:** evidence_planner.py:9, capability_library.py:6
- **Description:** Code comments reference `docs/ai/06_EVIDENCE_TEMPLATES.md` and `docs/ai/07_CAPABILITY_GRAPH.md` which don't exist.
- **DoD:** References either point to real docs or are removed.

### T-018 — Create .github/workflows/ci.yml
- **Source:** CHANGELOG.md claims it exists but doesn't
- **Description:** Create GitHub Actions CI workflow or update CHANGELOG.
- **DoD:** CI workflow exists and runs, or CHANGELOG corrected.

### T-019 — Fix tools.json/servers.json gitignore inconsistency
- **Source:** .gitignore lists both as ignored but both are committed
- **Description:** Either remove from gitignore or remove from tracking.
- **DoD:** Files match gitignore constraint.

### T-020 — Remove unused dependencies from pyproject.toml
- **Source:** Phase 0 discovery
- **Description:** numpy>=1.24 and requests>=2.31 are never imported.
- **DoD:** Only actually-used dependencies declared.

### T-021 — Remove Lovable AGENTS.md from ui/
- **Source:** 08_PROJECT_STATE.md claims it was removed but file still exists
- **Description:** ui/AGENTS.md contains Lovable instructions that should have been cleaned up.
- **DoD:** File removed.

### T-022 — Initialize _INTENT_PROMPTS at module level in prompt_builder_v2.py
- **Source:** Phase 0 discovery
- **Description:** Lazy-init pattern with side effects on first call.
- **DoD:** No lazy-init side effects on global dict.

### T-023 — Populate BACKLOG.md (this file) with proper content
- **Source:** Empty file at root
- **Description:** BACKLOG.md was empty; now populated with this task list.
- **DoD:** BACKLOG.md is the single source of truth for all remaining work.

### T-024 — Document .workflow directory in README
- **Source:** Phase 0 discovery
- **Description:** Autonomous development supervisor is undocumented.
- **DoD:** README or docs mention .workflow/ and its purpose.

---

## Summary

- **P0 tasks:** 8 (T-001 through T-008) — All testing coverage gaps
- **P1 tasks:** 7 (T-009 through T-016) — Code quality, stale docs, exception handling
- **P2 tasks:** 8 (T-017 through T-024) — Documentation, CI, cleanup
- **Total:** 23 tasks
