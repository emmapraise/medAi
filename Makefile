.PHONY: help test lint format install build-frontend build run dev qdrant v2 eval compose-up compose-down docker-build docker-run ingest clean

# Default port
PORT ?= 8000

help: ## Show this help message
	@echo "====================================================="
	@echo " 🩺 MediQA Bot — Makefile Commands"
	@echo "====================================================="
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

test: ## Run the backend test suite
	uv run pytest

lint: ## Lint backend (ruff) and frontend (oxlint)
	uv run ruff check .
	cd frontend && npm run lint

format: ## Auto-format and fix backend code
	uv run ruff check --fix .
	uv run ruff format .

install: ## Install backend (uv) and frontend dependencies
	uv sync
	cd frontend && npm install

build-frontend: ## Build React PWA production assets into frontend/dist
	cd frontend && npm run build

build: install build-frontend ## Complete install and build of frontend & backend

run: ## Run MediQA Bot application locally with uv
	uv run python main.py

dev: ## Run with hot-reloading for local development
	uv run uvicorn main:app --host 0.0.0.0 --port $(PORT) --reload

eval: ## Score the v2 retriever on the 105 retrieval cases (needs the local Qdrant index)
	uv run python eval/run_retrieval.py v2

qdrant: ## Start the local Qdrant container that v2 searches (no-op if it is already running)
	docker start qdrant_db

v2: qdrant ## Run MediQA v2 on http://localhost:8081 (local Qdrant, database from .env, no rate limit)
	RATE_LIMIT_ENABLED=false uv run uvicorn main:app --port 8081

compose-up: ## Start the full stack (App + PostgreSQL + Qdrant) via Docker Compose
	docker compose up --build

compose-down: ## Stop and remove all Docker Compose containers
	docker compose down

docker-build: ## Build standalone Docker container image
	docker build -t mediqa-bot:latest .

docker-run: ## Run the image locally on http://localhost:$(PORT) (the container listens on 7860)
	docker run -p $(PORT):7860 --env-file .env mediqa-bot:latest

ingest: ## Build or rebuild the v2 search index (V2_QDRANT_URL picks the Qdrant; ARGS=--resume continues a partial run)
	uv run python -m app.services.search_v2 $(ARGS)

clean: ## Clean cached python bytecode, frontend dist, and temporary artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf frontend/dist
