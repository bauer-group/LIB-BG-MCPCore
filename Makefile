# bg-mcpcore — development commands
.PHONY: help install install-dev lint format type-check test test-cov build clean pre-commit all-checks

help:
	@echo "bg-mcpcore development commands"
	@echo "  install      Install package in editable mode"
	@echo "  install-dev  Install with dev + docs extras + pre-commit"
	@echo "  lint         Run ruff linter"
	@echo "  format       Auto-fix lint issues with ruff"
	@echo "  type-check   Run mypy"
	@echo "  test         Run tests"
	@echo "  test-cov     Run tests with coverage"
	@echo "  build        Build sdist + wheel"
	@echo "  clean        Remove build/test artifacts"
	@echo "  all-checks   lint + type-check + test"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev,docs,openapi,redis,tasks,testkit]"
	pre-commit install

lint:
	ruff check src/ tests/

format:
	ruff check --fix src/ tests/

type-check:
	mypy src/bg_mcpcore/

test:
	pytest

test-cov:
	pytest --cov=src/bg_mcpcore --cov-report=term-missing --cov-report=html

build:
	python -m build

clean:
	rm -rf build/ dist/ *.egg-info/ htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +

pre-commit:
	pre-commit run --all-files

all-checks: lint type-check test
	@echo "All checks passed."
