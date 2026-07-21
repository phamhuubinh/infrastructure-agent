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
- **Stateless execution.** Each investigation is independent. No state persists between runs.
- **Evidence first.** Better tools → Better evidence → Better assessment.

## Before Committing

1. Run tests: `python -m pytest tests/ -q --tb=short -k "not slow"`
2. Run lint: `ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501`
3. Run typecheck: `make typecheck`
4. Run security scan: `make security-scan` (requires `pip install -e ".[security]"`)
5. Run full CI suite locally: `make ci` (test + lint + security-scan)
6. Update `docs/ai/08_PROJECT_STATE.md` if behavior changes
7. Update `CHANGELOG.md` for user-facing changes

## Commit Guidelines

- One logical change per commit
- Clear, descriptive commit messages
- Reference related issues or documents when appropriate
