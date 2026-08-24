# Contributing

## Development setup

```bash
pip install -e ".[test]"
python -m pytest tests/ -q --tb=short
ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501
```

## Architecture

Read `docs/README.md`, relevant ADRs/architecture docs, `docs/development/ENGINEERING_RULES.md`, and for current repair work `docs/development/IMPLEMENTATION_GAPS.md`.

The model owns language interpretation/reasoning/proposals. The harness owns active-stage validation, actual capability disclosure, exact capability/target/source authority, arguments, permission/approval, budgets, execution, evidence, and completion.

Do not add a language-specific semantic router. Natural language never authorizes shell/HTTP/database/file/infrastructure execution. Unknown/malformed authority state fails closed; no default localhost/source fallback.

Provider structured output does not remove harness validation. A capability that merely exists in the registry is not automatically disclosed.

## Before committing

1. Run affected unit/contract tests.
2. Run relevant lint/type/static checks.
3. For broad/destructive cleanup inspect callers/imports/static references.
4. Run `git diff --check` and review status/diff.
5. For repository-wide repair, run the full local unit/static suite when practical.
6. Update docs and implementation-gap ledger.
7. Regenerate generated artifacts through canonical generators.

Live smoke/E2E/Docker/model/tool QA remains a separate explicit gate.
