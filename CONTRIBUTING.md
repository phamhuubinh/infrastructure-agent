# Contributing

## Development setup

```bash
pip install -e ".[test]"

python -m pytest tests/ -q --tb=short

ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501
```

## Architecture

Start with `docs/README.md`, then read the relevant accepted ADRs and architecture documents.

The central boundary is:

> **The model owns language understanding, reasoning, and next-action proposals.**

> **The harness owns authority, validation, execution, evidence, limits, and completion.**

For normal configured requests, do not put a language-specific intent/target/source/freshness/
mutation/follow-up router in front of the model. The model proposes structured decisions; the
harness validates exact capability/target/source identities, arguments, permissions, budgets, and
safety before execution.

Natural-language text never authorizes shell, HTTP, database, file, or infrastructure operations.
READ/WRITE is determined by the reviewed capability effect, not by English/Vietnamese keyword
matching. Unknown identities fail closed; do not default to localhost or another source.

The accepted target architecture is under `docs/`. Current implementation facts come from code,
tests, generated API documentation, and runtime evidence. If they differ, document the gap instead
of adding compatibility behavior that violates an ADR.

## Before committing

1. Run the smallest affected unit/contract tests.
2. Run relevant lint/type/static checks for changed Python/TypeScript.
3. For destructive cleanup, inspect imports/callers/repository-wide references.
4. Run `git diff --check` and review `git status --short`.
5. Update current documentation when behavior changes.
6. Regenerate generated artifacts through their canonical generator when their source contract
   changes.
7. Update `CHANGELOG.md` for user-facing changes.

Smoke, E2E, Docker, full-QA, benchmark, and external-service validation are separate gates. Run them
only when the task explicitly requires that class of validation.

When a full QA run fails, fix the first real failure before treating later cascaded failures as
separate problems.

## Commit guidelines

- One logical change per commit.
- Use clear, descriptive commit messages.
- Do not preserve or reintroduce legacy architecture only for compatibility unless a real caller
  still requires it.
- Reference related issues, ADRs, or documents when useful.
