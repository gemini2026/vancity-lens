.PHONY: help dev up down logs test test-unit test-e2e seed build clean status frontend-logs api-logs db-logs shell-api shell-db lint

# Local dev API is exposed on the host at this port (see docker-compose.yml).
API_HOST_PORT ?= 8080
API_HOST_URL ?= http://localhost:$(API_HOST_PORT)

# ─── Default ─────────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Development ─────────────────────────────────────────────────
dev: ## Start full stack (db + api + frontend) with hot reload
	docker compose up --build

up: ## Start all services in background
	docker compose up -d --build

down: ## Stop all services
	docker compose down

clean: ## Stop all services and remove volumes
	docker compose down -v --remove-orphans
	docker compose --profile test down -v --remove-orphans

restart: ## Restart all services
	docker compose restart

status: ## Show service status
	@docker compose ps
	@echo ""
	@echo "────── Health Checks ──────"
	@curl -sf $(API_HOST_URL)/health > /dev/null 2>&1 && echo "✅ API:      $(API_HOST_URL)" || echo "❌ API:      not ready"
	@curl -sf http://localhost:3000 > /dev/null 2>&1 && echo "✅ Frontend: http://localhost:3000" || echo "❌ Frontend: not ready"

# ─── Logs ────────────────────────────────────────────────────────
logs: ## Tail all service logs
	docker compose logs -f

api-logs: ## Tail API logs only
	docker compose logs -f api

frontend-logs: ## Tail frontend logs only
	docker compose logs -f frontend

db-logs: ## Tail database logs only
	docker compose logs -f db

# ─── Testing ─────────────────────────────────────────────────────
test: test-unit ## Run unit tests

test-unit: ## Run Python unit tests
	python3 -m pytest tests/ -v --tb=short

test-e2e: ## Run Playwright E2E tests against local stack
	@echo "Ensuring local stack is running..."
	@docker compose up -d --build
	@echo "Waiting for services..."
	@sleep 5
	@until curl -sSf $(API_HOST_URL)/health | python3 -c 'import sys, json; sys.exit(0 if json.load(sys.stdin).get("status") == "ok" else 1)' 2>/dev/null; do echo "Waiting for API (/health status=ok)..."; sleep 2; done
	@until curl -sf http://localhost:3000 > /dev/null 2>&1; do echo "Waiting for Frontend..."; sleep 2; done
	@echo "Running Playwright E2E tests..."
	cd frontend && API_BASE_URL=$(API_HOST_URL) npx playwright test

test-e2e-docker: ## Run E2E tests in Docker container
	docker compose --profile test up --build --abort-on-container-exit e2e

test-e2e-ui: ## Run Playwright E2E tests with UI (headed mode)
	cd frontend && npx playwright test --ui

test-e2e-debug: ## Run Playwright E2E tests in debug mode
	cd frontend && npx playwright test --debug

# ─── Data Seeding ────────────────────────────────────────────────
seed: ## Seed database with sample intelligence data
	docker compose exec api python scripts/seed_data.py --scrape-only --source council --days-back 7

seed-all: ## Seed all data sources
	docker compose exec api python scripts/seed_data.py --scrape-only --source all --days-back 30

seed-status: ## Check data pipeline status
	docker compose exec api python scripts/seed_data.py --status

# ─── Intelligence Source Ingestion (config-driven) ────────────────
intel-dry-run: ## Show URLs that would be ingested from pipeline/sources.yaml
	docker compose exec api python scripts/ingest_sources.py --dry-run

intel-ingest: ## Ingest enabled sources from pipeline/sources.yaml (scrape only)
	docker compose exec api python scripts/ingest_sources.py

intel-ingest-process: ## Ingest + embed + extract signals (requires API keys)
	docker compose exec api python scripts/ingest_sources.py --process

# ─── Build ───────────────────────────────────────────────────────
build: ## Build all Docker images
	docker compose build

build-api: ## Build API image only
	docker compose build api

build-frontend: ## Build frontend image only
	docker compose build frontend

# ─── Shell Access ────────────────────────────────────────────────
shell-api: ## Open shell in API container
	docker compose exec api bash

shell-db: ## Open psql shell in database
	docker compose exec db psql -U vancity -d vancity_lens

shell-frontend: ## Open shell in frontend container
	docker compose exec frontend sh

# ─── Linting ─────────────────────────────────────────────────────
lint: ## Run linters (Python + TypeScript)
	@# `next lint` is interactive when no ESLint config exists; skip until the repo opts in.
	@if [ -f frontend/.eslintrc.json ] || [ -f frontend/.eslintrc.js ] || [ -f frontend/.eslintrc.cjs ] || [ -f frontend/.eslintrc.yml ] || [ -f frontend/.eslintrc.yaml ] || [ -f frontend/eslint.config.js ] || [ -f frontend/eslint.config.mjs ] || [ -f frontend/eslint.config.cjs ]; then \
		cd frontend && npx next lint 2>/dev/null || true; \
	else \
		echo "Skipping Next.js lint (no ESLint config in frontend/)"; \
	fi
	python3 -m flake8 api/ --max-line-length=120 --ignore=E501,W503 2>/dev/null || true

# ─── Database ────────────────────────────────────────────────────
db-reset: ## Reset database (destroy + recreate)
	docker compose down -v
	docker compose up -d db
	@echo "Waiting for DB to initialize..."
	@sleep 10
	docker compose up -d api frontend

db-migrate: ## Run SQL migrations manually
	@for f in db/0*.sql; do \
		echo "Running $$f..."; \
		docker compose exec -T db psql -U vancity -d vancity_lens -f /docker-entrypoint-initdb.d/$$(basename $$f); \
	done
