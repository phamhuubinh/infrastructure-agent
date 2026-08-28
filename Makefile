.PHONY: test lint typecheck acceptance qa-smoke qa-full openapi openapi-check architecture-check operations-check test-backend test-frontend lint-backend lint-frontend

test: test-backend test-frontend

test-backend:
	cd backend && PYTHONPATH=src ../.venv/bin/python -m pytest

test-frontend:
	cd ui && npm test -- --run

lint: lint-backend lint-frontend

lint-backend:
	cd backend && ../.venv/bin/ruff check src tests && ../.venv/bin/ruff format --check src tests && PYTHONPATH=src ../.venv/bin/python -m mypy src

lint-frontend:
	cd ui && npm run lint && npx tsc --noEmit && npm run build

typecheck:
	cd backend && PYTHONPATH=src ../.venv/bin/python -m mypy src

openapi:
	cd backend && PYTHONPATH=src ../.venv/bin/python scripts/openapi.py --write

openapi-check:
	cd backend && PYTHONPATH=src ../.venv/bin/python scripts/openapi.py

architecture-check:
	cd backend && PYTHONPATH=src ../.venv/bin/python scripts/architecture_check.py

operations-check:
	cd backend && PYTHONPATH=src ../.venv/bin/python scripts/operations_check.py

acceptance: openapi-check architecture-check operations-check test lint typecheck

qa-smoke:
	PYTHONPATH=backend/src .venv/bin/python scripts/qa/runner.py --mode smoke --fail-fast

qa-full:
	PYTHONPATH=backend/src .venv/bin/python scripts/qa/runner.py --mode full
