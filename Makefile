.PHONY: test lint typecheck

test:
	PYTHONPATH=src .venv/bin/python -m pytest

lint:
	ruff check src tests
	ruff format --check src tests
	PYTHONPATH=src .venv/bin/python -m mypy src

typecheck:
	PYTHONPATH=src .venv/bin/python -m mypy src
