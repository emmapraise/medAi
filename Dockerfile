# MediQA v2: the React PWA and the FastAPI app in one image.
# Runs on Hugging Face Spaces (listens on 7860) and on Cloud Run (which sets PORT).
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

# curl is only for the HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs containers as uid 1000. /app is owned by that user from the start: a later
# `chown -R` would copy the whole environment into a new image layer (it cost 416 MB).
RUN useradd -m -u 1000 user && mkdir /app && chown user:user /app
WORKDIR /app
USER user

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    FASTEMBED_CACHE_PATH=/app/models \
    APP_ENV=production \
    PORT=7860

# Runtime dependencies only (the lockfile's default groups minus dev): no torch, pandas or LangChain.
COPY --chown=user:user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

# Bake the embedding models into the image so start-up never downloads anything.
RUN .venv/bin/python -c "from fastembed import SparseTextEmbedding, TextEmbedding; \
TextEmbedding('BAAI/bge-small-en-v1.5'); SparseTextEmbedding('Qdrant/bm25'); print('models baked')"

COPY --chown=user:user app/ ./app/
COPY --chown=user:user main.py ./
COPY --chown=user:user --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/healthz" || exit 1

# One worker: the models are loaded per process, and the in-memory cache and rate limiter are per process too.
CMD ["sh", "-c", "exec .venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT} --timeout-keep-alive 120"]
