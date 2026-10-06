.PHONY: help install dev test typecheck lint run clean

PYTHON ?= python

help:
	@echo "Targets:"
	@echo "  install    Install the package (editable)"
	@echo "  dev        Install with dev + trash extras"
	@echo "  test       Run the test suite (pytest)"
	@echo "  typecheck  Run mypy --strict on the package"
	@echo "  run        Run sweep against the current directory (dry-run)"
	@echo "  clean      Remove build/test caches"

install:
	$(PYTHON) -m pip install -e .

dev:
	$(PYTHON) -m pip install -e ".[dev,trash]"

test:
	$(PYTHON) -m pytest

typecheck:
	$(PYTHON) -m mypy

run:
	$(PYTHON) -m sweep . --dry-run

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
