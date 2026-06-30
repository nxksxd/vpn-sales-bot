PYTHON ?= python3

.PHONY: install test lint typecheck compile check migrate

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	PYTHONPATH=. $(PYTHON) -m pytest -q

lint:
	ruff check bot tests scripts

typecheck:
	PYTHONPATH=. mypy bot || true

compile:
	$(PYTHON) -m compileall bot scripts tests

check: compile lint typecheck test

migrate:
	alembic upgrade head
