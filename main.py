from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.services.search_service import search_engine
from app.services.agent_service import agent_service
from app.routers import health, search, qa, ingest, analytics

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Medical QA API Server...")
    search_engine.initialize()
    agent_service.initialize()
    yield
    print("Shutting down Medical QA API Server...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A Production-Ready Medical QA API with Qdrant Hybrid Search, LangGraph Self-Corrective RAG, and PostgreSQL Analytics.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(search.router, prefix="/api/v1", tags=["Search"])
app.include_router(qa.router, prefix="/api/v1", tags=["QA Agent"])
app.include_router(ingest.router, prefix="/api/v1", tags=["Ingestion"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics & Cost Monitoring"])

@app.get("/")
def read_root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "docs_url": "/docs",
        "health_url": "/api/v1/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
