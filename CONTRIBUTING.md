# Contributing

## Development Setup

```bash
# Install the package in editable mode with test dependencies
pip install -e ".[test]"

# Run tests
python -m pytest tests/ -q --tb=short

# Lint
ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501
```

## Architecture

Read `docs/ai/00_BOOTSTRAP.md` first for reading order and conflict priority.

Key principles:
- **Code investigates. AI explains.** Investigation is deterministic. AI is only used for assessment.
- **Ephemeral execution.** Raw observations and runtime state do not persist as conversation memory; typed session context and valid fresh cache entries are explicit.
- **Evidence first.** Better tools → Better evidence → Better assessment.

## Before Committing

1. Run the smallest affected unit tests.
2. Run relevant lint and type checks for changed Python/TypeScript files.
3. Review `git diff --check` and `git status --short`.
4. Update current-state documentation when behavior changes.
5. Update `CHANGELOG.md` for user-facing changes.

Smoke, E2E, Docker, full-QA, benchmark, and external-service validation run
only when the task explicitly requires that class of test.

## Commit Guidelines

- One logical change per commit
- Clear, descriptive commit messages
- Reference related issues or documents when appropriate
