.DEFAULT_GOAL := help

# ─── helpers ────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "pii-protect — available commands"
	@echo ""
	@echo "  make setup     copy .env.example → .env (skip if .env exists)"
	@echo "  make start     build images + start all services + run migrations"
	@echo "  make stop      stop all services"
	@echo "  make restart   stop → start"
	@echo "  make migrate   run Alembic migrations"
	@echo "  make logs      tail API logs"
	@echo "  make test      run pytest inside the API container"
	@echo "  make clean     stop + remove volumes (destructive)"
	@echo ""

# ─── setup ──────────────────────────────────────────────────────────────────

.PHONY: setup
setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✓ .env created from .env.example"; \
		echo "  → Set PII_ENCRYPTION_KEY and PII_ADMIN_INITIAL_KEY before starting"; \
	else \
		echo "  .env already exists, skipping"; \
	fi

# ─── lifecycle ──────────────────────────────────────────────────────────────

.PHONY: start
start:
	@echo "→ Building and starting services..."
	docker compose up --build -d
	@echo "→ Waiting for API to be healthy..."
	@until curl -sf http://localhost:$$(grep PII_API_PORT .env 2>/dev/null | cut -d= -f2 || echo 15500)/health > /dev/null 2>&1; do \
		sleep 2; \
	done
	@echo ""
	@echo "✓ pii-protect is running"
	@echo "  API  → http://localhost:$$(grep PII_API_PORT .env 2>/dev/null | cut -d= -f2 || echo 15500)"
	@echo "  UI   → http://localhost:$$(grep PII_UI_PORT .env 2>/dev/null | cut -d= -f2 || echo 15501)"
	@echo "  Docs → http://localhost:$$(grep PII_API_PORT .env 2>/dev/null | cut -d= -f2 || echo 15500)/docs"

.PHONY: stop
stop:
	docker compose down

.PHONY: restart
restart: stop start

# ─── operations ─────────────────────────────────────────────────────────────

.PHONY: migrate
migrate:
	docker compose exec api alembic upgrade head

.PHONY: logs
logs:
	docker compose logs -f api

.PHONY: update
update:
	docker compose build --no-cache api
	docker compose up -d api

.PHONY: test
test:
	docker compose exec api pytest

.PHONY: test-e2e
test-e2e:
	pytest tests/e2e/test_api.py -v

.PHONY: test-e2e-ui
test-e2e-ui:
	pytest tests/e2e/test_ui.py -v

.PHONY: test-e2e-all
test-e2e-all:
	pytest tests/e2e/ -v

.PHONY: clean
clean:
	@echo "WARNING: This will delete all volumes (database data will be lost)."
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker compose down -v
