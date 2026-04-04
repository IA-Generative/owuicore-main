.PHONY: up-socle up-socle-full up-dev down logs ps register discover smoke-test deploy-socle deploy-plugins deploy help

COMPOSE = docker compose
COMPOSE_SEARCH = docker compose --profile search
COMPOSE_DEV = docker compose --profile dev

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Local dev ---

up-socle: ## Start socle (OpenWebUI + Keycloak + Pipelines)
	$(COMPOSE) up -d

up-socle-full: ## Start socle with search (SearXNG + Valkey)
	$(COMPOSE_SEARCH) up -d

up-dev: ## Start socle + register-watcher (hot-reload dev mode)
	$(COMPOSE_DEV) up -d

down: ## Stop all services
	docker compose --profile search --profile dev down

logs: ## Tail logs for all services
	$(COMPOSE_SEARCH) logs -f

ps: ## List running services
	$(COMPOSE_SEARCH) ps

# --- Plugin management ---

register: ## Register all plugins (tools, pipelines, model_tools) from discovered repos
	python3 scripts/register_plugins.py

discover: ## List discovered plugin repos
	bash scripts/discover_plugins.sh

# --- Testing ---

smoke-test: ## Run smoke tests against local socle
	bash scripts/smoke_test.sh

# --- K8s deployment ---

deploy-socle: ## Deploy socle to K8s (namespace owui-socle)
	bash deploy/deploy-k8s.sh

deploy-plugins: ## Deploy all discovered plugins to K8s
	bash deploy/deploy-plugins.sh

deploy: deploy-socle deploy-plugins ## Deploy socle + all plugins
