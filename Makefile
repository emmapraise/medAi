.PHONY: help test lint format install build-frontend build run dev compose-up compose-down docker-build docker-run ingest clean

# Default port
PORT ?= 8000

help: ## Show this help message
	@echo "====================================================="
	@echo " 🩺 MediQA Bot — Makefile Commands"
	@echo "====================================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

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

compose-up: ## Start the full stack (App + PostgreSQL + Qdrant) via Docker Compose
	docker compose up --build

compose-down: ## Stop and remove all Docker Compose containers
	docker compose down

docker-build: ## Build standalone Docker container image
	docker build -t mediqa-bot:latest .

docker-run: ## Run standalone Docker container locally
	docker run -p $(PORT):8080 --env-file .env mediqa-bot:latest

ingest: ## Trigger dataset ingestion into Qdrant Cloud knowledge base
	uv run python -c "from app.services.search_service import search_engine; search_engine.initialize(); search_engine.ingest_dataset('dataset/medquad.csv')"

clean: ## Clean cached python bytecode, frontend dist, and temporary artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf frontend/dist
