# CI/CD Pipeline

`.github/workflows/ci.yml` runs on pushes and pull requests to `main`.

## Jobs

### Python matrix

Python 3.10, 3.11, and 3.12 each run:

- `ruff check .`
- `python -m mypy src --ignore-missing-imports`
- Bandit, Safety, and `pip-audit`
- `pytest tests/` with XML and HTML coverage artifacts

`pip-audit` uses its supported default exit behavior. It does not use the nonexistent `--fail-on=high` option.

### RAG

Python 3.12 installs the committed `src/tool/RAGTool/uv.lock` with `uv sync --frozen --group dev` and runs the independent offline RAG suite under `src/tool/RAGTool/tests/`.

### UI

Node 22 runs `npm ci`, ESLint, Vitest, and the production client/SSR build.

### Desktop

Node 22 installs the pinned Electron dependencies, verifies the Docker reverse-proxy API contract, builds the UI, packages an unpacked Linux Electron application, and uploads it as an artifact. The checked-in `electron-builder` configuration also defines a Windows NSIS `OrionSetup` target.

### Containers

One job builds the API, UI, and RAG images. A second loads those images, starts the full Compose stack with CI-only secrets, waits for `/api/health`, runs smoke tests through direct API and reverse-proxy URLs, prints logs on failure, and removes containers/volumes afterward.

## Local equivalents

```bash
ruff check .
python3 -m mypy src --ignore-missing-imports
python3 -m pytest tests/ -q --tb=short

cd src/tool/RAGTool
uv sync --frozen --group dev
uv run pytest tests -q --tb=short

cd ../../desktop
npm ci
npm test

cd ui
npm ci
npm run lint
npm test -- --run
npm run build
```

Compose validation:

```bash
POSTGRES_PASSWORD=test-only ORION_API_KEY=test-only \
  ORION_TOOL_SECRETS_FILE=tests/data/empty_tool_credentials.json \
  docker compose config --quiet
```

> Last updated: 2026-08-08
