# accounts — developer convenience wrapper around docker compose.
# All compose files live in ./deploy. Local entrypoint: http://localhost:8085
# (8080 belongs to the 3m4 shortener stack, 8081 to exp, 8082 to retro, 8083 to
# metrics, on the same machine). Mailpit (local mail sink): http://localhost:8025

# --env-file makes the repo-root .env drive build-arg interpolation (VITE_* are
# inlined into the web bundle at build time), not just runtime container env.
COMPOSE      := docker compose --env-file .env -f deploy/docker-compose.yml
BASE_URL     ?= http://localhost:8085

.PHONY: help up down build rebuild logs ps migrate prune genkey shell-api shell-db clean widget smoke e2e test

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

migrate: ## Run create-all + alembic upgrade
	$(COMPOSE) run --rm migrate python -m dbcore.cli upgrade

prune: ## Delete expired sessions / email tokens and delivered outbox rows
	$(COMPOSE) run --rm migrate python -m dbcore.cli prune

genkey: ## Print a fresh Ed25519 signing key (SESSION_SIGNING_KEY)
	$(COMPOSE) run --rm --no-deps migrate python -m dbcore.cli genkey

shell-api: ## Shell into the api container
	$(COMPOSE) exec api sh

shell-db: ## psql into Postgres
	$(COMPOSE) exec postgres psql -U accounts -d accounts

clean: ## Stop and remove volumes (DESTRUCTIVE: wipes the database)
	$(COMPOSE) down -v

widget: ## Build session.js into apps/web/public
	cd packages/session-js && bun install && bun run build

smoke: ## Curl the running stack: health, JWKS, session.js headers, signup → session → logout (BASE_URL)
	BASE_URL=$(BASE_URL) sh deploy/smoke.sh

e2e: ## Run the Playwright end-to-end suite against the running stack (E2E_BASE_URL)
	cd e2e && bun install && bunx playwright install chromium && bun run test

test: ## Run the API pytest suite against a disposable Postgres + Redis (no stack needed)
	sh deploy/test.sh
