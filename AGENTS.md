# AGENTS.md — Codex Instructions for Orion

This file defines repository-level instructions for OpenAI Codex when working on Orion.

## 1. Read project context first

Before changing code, understand the existing project and follow the repository's documented architecture.

Read in this order when relevant:

1. `docs/ai/00_BOOTSTRAP.md`
2. `docs/ai/07_DEVELOPMENT_RULES.md`
3. `docs/ai/08_PROJECT_STATE.md`
4. `README.md`
5. Relevant files under `docs/`
6. Relevant implementation and tests

Do not scan unrelated directories unnecessarily. Ignore generated/cache/vendor directories such as `.git/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, and `node_modules/` unless the task specifically requires them.

## 2. Core engineering rules

- Do not change architecture unless the user explicitly asks for or approves an architectural change.
- Do not create duplicate implementations when an existing abstraction can be reused.
- Prefer deterministic logic over AI/LLM behavior when deterministic logic is sufficient.
- Preserve existing interfaces and behavior unless the task requires changing them.
- Keep changes narrowly scoped to the user's request.
- Do not make unrelated cleanup or refactors while completing another task.
- Do not modify generated files unless the task explicitly requires it.
- Explain important assumptions or tradeoffs in the final response.

## 3. Testing policy — IMPORTANT

### Never run smoke tests automatically

Codex MUST NOT run smoke tests, full QA suites, E2E tests, integration environments, or other expensive/system-level validation unless the user explicitly asks for that exact class of testing in the current request.

In particular, DO NOT automatically run:

- `make qa-smoke`
- `make qa-full`
- `python3 scripts/qa/ga2_runner.py --mode smoke ...`
- `python3 scripts/qa/unified_qa.py`
- E2E/browser tests
- Docker-based test environments
- `docker compose up`, `docker-compose up`, or equivalent service startup for validation
- Electron/UI application startup for validation
- benchmarks unless explicitly requested
- security scans that install packages or contact external services unless explicitly requested

Do not run one of the above merely because a task is complete, because a test failed, or because additional confidence would be useful.

### Do not ask to run prohibited validation

Codex MUST NOT ask for permission to run smoke tests, full QA, E2E,
Docker-based validation, integration environments, benchmarks, or other
prohibited validation merely because they are the next project/release step.

If such validation is required to complete a later release gate:

- stop at the code-complete boundary;
- state that the release gate remains pending;
- state which validation was not run;
- provide the exact command(s) a maintainer may run manually, if useful;
- do not ask "should I run it?", "do you want me to run it?", or equivalent;
- do not treat the pending release gate as permission to continue into it.

Only run prohibited validation when the user's current message explicitly
requests that validation class.

**Smoke testing requires an explicit user request. Absence of a prohibition is not permission.**

### Allowed default validation

After a code change, Codex may run the smallest relevant local checks needed to catch obvious regressions, for example:

- targeted pytest tests for the files/components changed
- the repository's normal affected unit tests
- `ruff check` on changed/relevant Python files
- `ruff format --check` on changed/relevant Python files
- targeted TypeScript type checking when TypeScript code was changed
- syntax/import/compile checks that do not start external services

Prefer targeted checks over the entire test suite.

The repository rule to run affected tests does NOT imply permission to run smoke, E2E, full QA, Docker, browser, Electron, benchmark, or external-service tests.

If the only meaningful validation would require a prohibited test class, do not run it. State in the final response that it was not run and why.

## 4. Commands and side effects

Do not automatically:

- start long-running servers or development processes
- start Docker containers
- open browsers or GUI applications
- install system packages
- install or upgrade project dependencies unless required by the requested task
- modify credentials, secrets, `.env` files, or machine-level configuration
- perform network-dependent validation unless it is necessary and explicitly requested
- delete user data or reset persistent state

For ordinary code inspection, editing, and lightweight local validation, proceed without asking unnecessary confirmation.

## 5. Git policy

- Review the relevant diff after making changes.
- Do not commit, push, force-push, rebase, reset, create branches, or modify remote state unless the user explicitly asks.
- Do not revert unrelated changes already present in the working tree.
- Keep edits atomic and limited to the task.

If the user explicitly requests a commit, create one logical commit for the requested task unless instructed otherwise.

## 6. Project-state documentation

Update `docs/ai/08_PROJECT_STATE.md` only when the completed change actually changes the documented project state.

Do not update project status merely to describe planned or incomplete work.

## 7. Completion criteria

A task is complete when:

1. The requested change is implemented.
2. The diff has been reviewed for accidental/unrelated edits.
3. Appropriate lightweight validation has been run where practical.
4. Prohibited smoke/E2E/full-QA validation has NOT been run unless explicitly requested.
5. The final response clearly states what changed and which validation commands, if any, were actually run.

Never claim a test passed unless it was actually executed successfully.

A coding task may be considered code-complete even when a separate release
gate remains pending.

Do not attempt or request permission to cross a release gate unless the
user explicitly asks for release validation.

## 8. User instruction priority

The user's current explicit request takes priority over defaults in this file, provided it is safe and feasible.

Examples:

- "Run the smoke test" → running `make qa-smoke` is permitted for that request.
- "Fix this bug" → smoke testing is NOT implicitly permitted.
- "Run all tests" → clarify through the command scope only if necessary; do not silently interpret it as permission to start Docker/E2E/system environments unless those are clearly part of the requested suite.

When uncertain whether a command qualifies as smoke/E2E/full QA or starts external services, treat it as prohibited by default and use a smaller local check instead.
