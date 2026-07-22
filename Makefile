PYTHON ?= python
PNPM ?= pnpm

.PHONY: install install-local lint typecheck test web demo run ci docker

install:
	$(PYTHON) -m pip install -e ".[dev]"
	cd web && $(PNPM) install --frozen-lockfile

install-local:
	$(PYTHON) -m pip install -e ".[local,dev]"
	cd web && $(PNPM) install --frozen-lockfile

lint:
	$(PYTHON) -m ruff check .
	cd web && $(PNPM) lint

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest

web:
	cd web && $(PNPM) build

demo:
	$(PYTHON) scripts/create_demo_fixture.py

run: web
	$(PYTHON) -m uvicorn arabic_schoolbook_ocr.api:app --host 127.0.0.1 --port 8000

ci: lint typecheck test web demo

docker:
	docker compose build
