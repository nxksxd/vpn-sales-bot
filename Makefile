PYTHON ?= python3

.PHONY: install test lint typecheck compile check migrate

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -q

lint:
	ruff check bot tests scripts

typecheck:
	mypy bot

compile:
	$(PYTHON) -m compileall bot scripts tests

check: compile lint typecheck test

migrate:
	alembic upgrade head
