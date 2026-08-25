.PHONY: test lint typecheck test-backend test-frontend lint-backend lint-frontend

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
