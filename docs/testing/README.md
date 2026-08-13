# Testing Guide

Orion separates deterministic local checks from environment-dependent QA.

## Python unit and contract tests

```bash
# Whole Python suite
python3 -m pytest tests/ -q --tb=short

# Affected areas
python3 -m pytest tests/pipeline/ -q --tb=short
python3 -m pytest tests/tool/ -q --tb=short
python3 -m pytest tests/backend/ -q --tb=short

# Coverage
python3 -m pytest tests/ --cov=src --cov-report=term-missing -q
```

The top-level suite contains agent, backend, benchmark-helper, CLI, model,
pipeline, QA-schema, security, shared-contract, and tool tests. Container smoke
tests live in the suite but skip unless their required environment is present.

## Static checks

```bash
ruff check .
python3 -m mypy src --ignore-missing-imports

cd ui
npm run lint
npx tsc --noEmit
```

## UI and Desktop

```bash
cd ui
npm test -- --run
npm run build

cd ../desktop
npm test
```

The UI uses Vitest and produces both client and SSR output. Desktop tests cover
the installed Docker reverse-proxy/API contract without starting Electron.

## RAG service

The RAG service has an independent locked environment:

```bash
cd src/tool/RAGTool
uv sync --frozen --group dev
uv run pytest tests -q --tb=short
```

Its default test configuration uses offline providers.

## Benchmark code

`tests/benchmark/` tests benchmark scoring/reporting code without constituting
a model benchmark run:

```bash
python3 -m pytest tests/benchmark/ -q --tb=short
```

The runtime benchmark entry point is `python3 -m benchmark`; it can call a
configured model/infrastructure and writes results under `benchmark_results/`.

## Manual QA

`scripts/qa/` contains configured-target/model runners. They can start Docker
or make real outbound requests and write ignored artifacts under
`artifacts/qa/`. They are not part of ordinary unit validation.

## Test-writing contract

- Name files `test_<module>.py` and tests `test_<behavior>`.
- Prefer deterministic fixtures and explicit typed-result assertions.
- Mock network, model, subprocess, and external API boundaries in unit tests.
- Cover success, valid-empty, partial, typed failure, unsafe input, and
  redaction behavior where the contract exposes those states.
- Use thread barriers/locks for concurrency tests instead of timing-only sleeps.
- Never claim a check passed unless its command was executed successfully.

CI job details are documented in `docs/devops/ci.md`.
