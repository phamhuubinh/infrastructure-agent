.PHONY: test lint typecheck clean build benchmark ci install dev-install

VENV = .venv
PYTHON = python3

test:
	$(PYTHON) -m pytest tests/ -q --tb=short -x

test-coverage:
	$(PYTHON) -m pytest tests/ --cov=src --cov-report=term-missing -q --tb=short

lint:
	ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501
	ruff format --check src/ tests/

lint-fix:
	ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501 --fix
	ruff format src/ tests/

typecheck:
	cd ui && npx tsc --noEmit 2>/dev/null || true

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache .ruff_cache

build:
	$(PYTHON) -m build

benchmark:
	$(PYTHON) -m pytest tests/benchmark/ -q --tb=short

desktop-install:
	cd desktop && npm install

desktop-start:
	cd desktop && npx electron .

security-scan:
	pip install bandit safety pip-audit -q
	bandit -r src/ -c pyproject.toml --severity-level high -f sarif -o bandit_results.sarif || true
	safety check --full-report --exit-code || true
	pip-audit --strict || true

ci: test lint security-scan typecheck

install:
	pip install -e ".[test]"

dev-install:
	pip install -e ".[test]"
	pip install pytest-cov build
