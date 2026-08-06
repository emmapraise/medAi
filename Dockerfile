# Multi-stage Dockerfile for MediQA Bot (React PWA + FastAPI)
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

# Copy official uv binary from Astral
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy lockfiles and install dependencies via uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

# Copy application source code and built frontend dist
COPY app/ ./app/
COPY main.py ./main.py
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

ENV PORT=8000
EXPOSE ${PORT}
CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
