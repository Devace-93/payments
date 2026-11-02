# payments — developer convenience wrapper around docker compose.
# All compose files live in ./deploy. Local entrypoint: http://localhost:8086
# (8080 belongs to the 3m4 shortener stack, 8081 to exp, 8082 to retro, 8083 to
# metrics, 8085 to accounts, on the same machine). Mailpit (local mail sink):
# http://localhost:8026

# --env-file makes the repo-root .env drive build-arg interpolation (VITE_* are
# inlined into the web bundle at build time), not just runtime container env.
COMPOSE      := docker compose --env-file .env -f deploy/docker-compose.yml
BASE_URL     ?= http://localhost:8086

.PHONY: help up down build rebuild logs ps migrate sync-catalog create-prices app-key seed-completed prune shell-api shell-db clean widget smoke e2e test lint stripe-listen

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Build + start the full stack (api, worker, web, caddy, mailpit)
	@docker network inspect edge >/dev/null 2>&1 || docker network create edge >/dev/null
	$(COMPOSE) up -d --build

down: ## Stop the stack
	$(COMPOSE) down

build: ## Rebuild all images
	$(COMPOSE) build

rebuild: ## Rebuild from scratch (no cache)
	$(COMPOSE) build --no-cache

logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

migrate: ## Run create-all + alembic upgrade, then sync the catalog
	$(COMPOSE) run --rm migrate sh -c "python -m dbcore.cli upgrade && python -m dbcore.cli sync-catalog"

sync-catalog: ## Mirror packages/shared/catalog.json into the DB (resolves Stripe price ids by lookup key)
	$(COMPOSE) run --rm migrate python -m dbcore.cli sync-catalog

create-prices: ## Create the missing Stripe products/prices from catalog.json (sandbox or live, once each)
	$(COMPOSE) run --rm migrate python -m dbcore.cli create-prices

app-key: ## Rotate an app's service key + webhook secret: make app-key SLUG=retro [WEBHOOK_URL=https://retro.3m4.net/api/billing/webhook]
	@test -n "$(SLUG)" || { echo "usage: make app-key SLUG=<slug> [WEBHOOK_URL=...]"; exit 2; }
	$(COMPOSE) run --rm migrate python -m dbcore.cli app-key $(SLUG) $(WEBHOOK_URL)

seed-completed: ## Fake-Stripe helper: complete a checkout as if Stripe had: make seed-completed CS=cs_fake_...
	@test -n "$(CS)" || { echo "usage: make seed-completed CS=<cs_id>"; exit 2; }
	$(COMPOSE) run --rm migrate python -m dbcore.cli seed-completed $(CS)

prune: ## Delete finished outbox rows, stale checkouts/events and dead claim codes
	$(COMPOSE) run --rm migrate python -m dbcore.cli prune

shell-api: ## Shell into the api container
	$(COMPOSE) exec api sh

shell-db: ## psql into Postgres
	$(COMPOSE) exec postgres psql -U payments -d payments

clean: ## Stop and remove volumes (DESTRUCTIVE: wipes the database)
	$(COMPOSE) down -v

widget: ## Build pay.js into apps/web/public
	cd packages/pay-js && bun install && bun run build

smoke: ## Curl the running stack: health, catalog, pay.js headers, badge (BASE_URL)
	BASE_URL=$(BASE_URL) sh deploy/smoke.sh

e2e: ## Run the Playwright end-to-end suite against the running stack (E2E_BASE_URL)
	cd e2e && bun install && bunx playwright install chromium && bun run test

test: ## Run the API pytest suite against a disposable Postgres + Redis (no stack needed)
	sh deploy/test.sh

lint: ## ruff over the Python side (uses .venv from `make test`)
	.venv/bin/ruff check dbcore services/api db packages/relying-party/python

stripe-listen: ## Forward Stripe sandbox webhooks to the local stack (needs the Stripe CLI, logged in)
	stripe listen --forward-to localhost:8086/api/stripe/webhook
