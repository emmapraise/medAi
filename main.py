import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings
from app.services.search_service import search_engine
from app.services.agent_service import agent_service
from app.routers import health, search, qa, ingest

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Search Engine & AI Agent on application startup
    search_engine.initialize()
    agent_service.initialize()
    yield
    print("[App] Shutting down Medical QA Service...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Modular & Optimized FastAPI for Medical Question-Answering powered by Qdrant Hybrid Search & Gemini LLMs.",
    version=settings.VERSION,
    lifespan=lifespan
)

# Include Routers with API Prefix /api/v1
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(search.router, prefix="/api/v1", tags=["Search"])
app.include_router(qa.router, prefix="/api/v1", tags=["Agent QA"])
app.include_router(ingest.router, prefix="/api/v1", tags=["Admin Ingestion"])

@app.get("/", tags=["Root"])
def root():
    return {
        "title": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "status": "online"
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
