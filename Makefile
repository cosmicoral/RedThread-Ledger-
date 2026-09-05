.PHONY: demo demo-backend demo-frontend demo-docker sync-data test eval lint help

COMPOSE ?= docker compose
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
DATASET_ROOT ?= /Users/yuhan/Downloads/Ylookup Hackathon Datasets/01-bank-statements-to-journal-entries

help:
	@echo "RedThread Ledger"
	@echo ""
	@echo "  make demo       Start the app from committed runtime data (http://localhost:3000)"
	@echo "  make sync-data  Optional: refresh PDFs/CSVs and copy the eval workbook"
	@echo "  make test       Run unit and integration tests"
	@echo "  make eval       Evaluate against held-out statements"
	@echo "  make lint       Run code-quality checks"
	@echo "  make demo-docker  Start via docker compose"

sync-data:
	DATASET_ROOT="$(DATASET_ROOT)" PYTHONPATH=backend $(PYTHON) -m reference.sync

demo:
	$(MAKE) -j2 demo-backend demo-frontend

demo-backend:
	PYTHONPATH=backend $(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000

demo-frontend:
	cd frontend && npm install --no-fund --no-audit && npm run dev

demo-docker:
	$(COMPOSE) up --build

test:
	PYTHONPATH=backend:$(CURDIR) $(PYTHON) -m pytest tests -q

eval:
	PYTHONPATH=backend:$(CURDIR) $(PYTHON) -m evaluation.harness

lint:
	$(PYTHON) -m ruff check backend tests evaluation
	cd frontend && npm run lint
