# AGENTS.md — Repository instructions for Orion

This file defines repository-level instructions for AI coding agents working on Orion.

## 1. Read project context first

Before changing code, understand the accepted architecture and the current implementation.

Read in this order when relevant:

1. `docs/README.md` — documentation scope, reading order, and conflict priority.
2. Relevant accepted ADRs under `docs/decisions/`.
3. Relevant architecture documents under `docs/architecture/`.
4. `docs/development/ENGINEERING_RULES.md`.
5. Relevant development/migration/testing documents under `docs/development/`.
6. `README.md` for current operator/product behavior.
7. Relevant implementation and tests.

Do not infer current implementation state from an old roadmap or historical changelog entry. Source
code, tests, generated API documentation, and runtime evidence establish implementation facts.
Accepted ADRs remain authoritative for target architecture.

Ignore generated/cache/vendor directories such as `.git/`, `.venv/`, `__pycache__/`,
`.pytest_cache/`, `.ruff_cache/`, and `node_modules/` unless the task requires them.

## 2. Core architecture rules

- **Model semantics, deterministic authority.** For normal configured requests, the model owns
  natural-language interpretation, reasoning, and next-action proposals. The harness owns
  authority, exact validation, execution, evidence, limits, and completion.
- Do not add a semantic pre-router that decides intent, target, source, freshness/currentness,
  mutation meaning, tool family, or follow-up meaning from prose before the model.
- Natural-language text is not execution authority. Execute only structured actions that passed the
  canonical validator.
- Capability/target/source identities resolve exactly. Never add fuzzy authorization, silent source
  fallback, or default-localhost behavior.
- READ/WRITE is an effect classification of reviewed capabilities, not a keyword classifier.
- Tool integrations own commands/API behavior. The model does not receive raw shell, HTTP,
  credential, or database authority.
- Preserve evidence status, time, target/source, and provenance. Never turn failure or stale data
  into a healthy-looking result.
- Do not expose secrets or private chain-of-thought to model context, public traces, logs, or UI.
- Keep provider-specific behavior behind model adapters.
- Do not recreate legacy deterministic/semantic routing or compatibility shells merely to make a
  test pass.
- Compatibility code may exist only while real callers require it; remove it after caller/import
  analysis proves it is dead.
- Keep changes narrowly scoped. Do not make unrelated refactors during another task.

## 3. Testing policy — IMPORTANT

### Never run smoke/full runtime QA automatically

Do not run smoke tests, full QA, E2E, Docker-based runtime validation, benchmarks, browser/Electron
flows, or external-service tests unless the user's current request explicitly asks for that class
of validation.

In particular, do not automatically run:

- `make qa-smoke`
- `make qa-full`
- `python3 scripts/qa/ga2_runner.py --mode smoke ...`
- `python3 scripts/qa/unified_qa.py`
- E2E/browser tests
- Docker Compose startup for validation
- Electron/UI startup for validation
- live benchmarks
- network-dependent security scans

Do not ask for permission to cross a release/runtime QA gate merely because it is the next step.
Stop at the code-complete boundary, state the pending gate, and provide the exact manual command when
useful.

### Allowed default validation

After a code change, run the smallest relevant local checks needed to catch regressions:

- targeted pytest tests for changed components;
- relevant unit/contract tests;
- targeted `ruff check` / `ruff format --check`;
- targeted TypeScript type checking;
- syntax/import/collection checks that do not start external services.

For destructive refactors or legacy cleanup, also check the caller/import graph and repository-wide
static references, then run `git diff --check`. Full suite/runtime QA remains a separate gate unless
explicitly requested.

When a full QA run is explicitly requested and fails, isolate the first real failure before treating
later cascaded failures as separate architecture problems.

Never claim a test passed unless it was actually executed successfully.

## 4. Commands and side effects

Do not automatically:

- start long-running servers;
- start Docker containers;
- open browsers or GUI applications;
- install system packages;
- install/upgrade dependencies unless required by the task;
- modify credentials, secrets, `.env`, or machine-level configuration;
- delete user data or reset persistent state.

For ordinary inspection, editing, and lightweight local validation, proceed without unnecessary
confirmation.

## 5. Git policy

- Review the relevant diff after making changes.
- Do not commit, push, force-push, rebase, reset, create branches, or modify remote state unless the
  user explicitly requests it.
- Do not revert unrelated working-tree changes.
- Keep edits atomic and limited to the task.

## 6. Documentation policy

When behavior or architecture changes:

- update the relevant current documentation;
- update an ADR only through an explicit superseding decision when architecture changes;
- regenerate generated artifacts such as OpenAPI through their canonical generator rather than
  hand-editing them;
- distinguish accepted target architecture from current implementation gaps;
- do not resurrect references to the removed legacy AI-documentation hierarchy.

## 7. Completion criteria

A coding task is complete when the requested change is implemented, the diff is reviewed, appropriate
lightweight validation has run where practical, and the response states exactly what was and was not
validated.

A separate runtime/release gate may remain pending. Do not cross it unless the user's current request
explicitly includes that validation.

## 8. User instruction priority

The user's current explicit request takes priority over repository defaults when safe and feasible.
For example, an explicit request to run GA2 permits GA2; an ordinary bug fix does not.
