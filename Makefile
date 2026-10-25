# ==============================================================================
# PS-05 Digital Evidence Verification Platform - Master Makefile
# ==============================================================================

SHELL := /bin/bash
PYTHON ?= ./.venv/bin/python
PIP ?= ./.venv/bin/pip
PYTEST ?= ./.venv/bin/pytest
RUFF ?= ./.venv/bin/ruff
MYPY ?= ./.venv/bin/mypy
NPM ?= npm
DOCKER_COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "PS-05 Digital Evidence Verification Platform"
	@echo "---------------------------------------------"
	@echo "Available commands:"
	@echo "  make setup       - Install Python virtualenv, backend & frontend dependencies"
	@echo "  make dev         - Start local development services (docker-compose)"
	@echo "  make test        - Execute backend test suite"
	@echo "  make lint        - Run Python and frontend linters"
	@echo "  make typecheck   - Run mypy and TypeScript compiler checks"
	@echo "  make migrate     - Run database migrations via Alembic"
	@echo "  make down        - Stop containers and networks; preserve volumes"
	@echo "  make reset-data  - DESTRUCTIVE: remove containers AND database/Redis volumes"

.PHONY: setup
setup:
	@echo "==> Setting up private storage vaults..."
	@mkdir -p storage/originals storage/artifacts storage/reports storage/tmp
	@echo "==> Setting up backend Python environment..."
	@python -m venv .venv || python3 -m venv .venv
	@$(PIP) install --upgrade pip
	@$(PIP) install -r services/api/requirements-dev.txt
	@echo "==> Setting up frontend web environment..."
	@cd apps/web && $(NPM) install
	@echo "==> Setup complete!"

.PHONY: dev
dev:
	@echo "==> Starting infrastructure services (PostgreSQL & Redis)..."
	@$(DOCKER_COMPOSE) up -d db redis
	@echo "==> Run backend: (cd services/api && uvicorn app.main:app --reload)"
	@echo "==> Run frontend: (cd apps/web && npm run dev)"

.PHONY: test
test:
	@echo "==> Running backend Pytest suite..."
	@cd services/api && ../../$(PYTHON) -m pytest -v

.PHONY: lint
lint:
	@echo "==> Running backend ruff linter..."
	@cd services/api && ../../$(RUFF) check .
	@echo "==> Running frontend eslint..."
	@cd apps/web && $(NPM) run lint

.PHONY: typecheck
typecheck:
	@echo "==> Running backend strict mypy type checking..."
	@cd services/api && ../../$(MYPY) app tests
	@echo "==> Running frontend TypeScript compilation check..."
	@cd apps/web && $(NPM) run typecheck

.PHONY: migrate
migrate:
	@echo "==> Running database migrations..."
	@cd services/api && ../../$(PYTHON) -m alembic upgrade head

.PHONY: down
down:
	@echo "==> Stopping Docker Compose services without deleting persistent data..."
	@$(DOCKER_COMPOSE) down

.PHONY: reset-data
reset-data:
	@echo "WARNING: This deletes PostgreSQL and Redis Compose volumes."
	@printf "Type DELETE-DATA to continue: "; \
	read -r confirm; \
	if [ "$confirm" = "DELETE-DATA" ]; then \
		$(DOCKER_COMPOSE) down -v; \
	else \
		echo "Cancelled; persistent data was preserved."; \
		exit 1; \
	fi
