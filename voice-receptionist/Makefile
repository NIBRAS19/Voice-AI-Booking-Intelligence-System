# Voice AI - Developer Makefile

.PHONY: help setup dev prod test lint clean db-up db-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and setup environment
	pip install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env; fi
	cd admin-dashboard && npm install

dev: ## Start local development server (background)
	docker compose up -d
	cd admin-dashboard && npm run dev

dev-logs: ## View backend logs
	docker compose logs -f api

prod: ## Deploy using production configuration
	./scripts/deploy.sh deploy

test: ## Run all tests
	./scripts/run_tests.ps1 all

test-unit: ## Run unit tests only
	./scripts/run_tests.ps1 unit

test-int: ## Run integration tests only
	./scripts/run_tests.ps1 integration

lint: ## Run code linter
	flake8 src tests
	black --check src tests

format: ## Format code
	black src tests

db-up: ## Start database only
	docker compose up -d db redis

db-down: ## Stop database
	docker compose stop db redis

clean: ## Remove temporary files
	rm -rf __pycache__ .pytest_cache
	rm -rf src/**/__pycache__
