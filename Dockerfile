# Multi-stage Dockerfile for MediQA Bot (React PWA + FastAPI)
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

# Copy official uv binary from Astral
COPY --from=ghcr.io/astral-sh/uv:0.11  /uv /uvx /bin/

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy lockfiles and install dependencies via uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

# Pre-download & save model weights during Docker BUILD time into /app/models/pubmedbert-onnx
# This runs during Cloud Build (which has 8-16GB RAM), baking the ONNX files into the image.
# At runtime on Cloud Run, it boots in seconds using ONLY ~900MB RAM!
RUN uv run python -c "\
from sentence_transformers import SentenceTransformer; \
from fastembed import SparseTextEmbedding; \
print('Baking ONNX model into container image at build time...'); \
model = SentenceTransformer('emmapraise/pubmedbert-base-embeddings-onnx', backend='onnx', model_kwargs={'provider': 'CPUExecutionProvider'}); \
model.save_pretrained('/app/models/pubmedbert-onnx'); \
SparseTextEmbedding('Qdrant/bm25'); \
print('Build-time model caching complete.')"

# Copy application source code and built frontend dist
COPY app/ ./app/
COPY main.py ./main.py
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Run as an unprivileged user
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8080}/healthz" || exit 1

CMD ["sh", "-c", "uv run --frozen --no-dev uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --timeout-keep-alive 120"]
