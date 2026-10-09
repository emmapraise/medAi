import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langfuse import get_client

from app.config import settings
from app.logging_config import configure_logging
from app.routers import analytics, health, ingest, qa, search
from app.services.agent_service import agent_service
from app.services.search_service import search_engine

configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Medical QA Server")
    # Run both initializations concurrently but WAIT for them to finish
    # before accepting traffic. This prevents "connection error" on first request.
    loop = asyncio.get_running_loop()
    await asyncio.gather(
        loop.run_in_executor(None, search_engine.initialize),
        loop.run_in_executor(None, agent_service.initialize),
    )
    logger.info("All services ready; accepting requests")
    yield
    logger.info("Shutting down Medical QA Server")
    try:
        get_client().flush()
    except Exception:
        logger.warning("Langfuse flush failed on shutdown", exc_info=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A Production-Ready Medical QA API & React PWA Application with LangGraph CRAG & PostgreSQL Analytics.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# API Routers
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(search.router, prefix="/api/v1", tags=["Search"])
app.include_router(qa.router, prefix="/api/v1", tags=["QA Agent"])
app.include_router(ingest.router, prefix="/api/v1", tags=["Ingestion"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics & Cost Monitoring"])

# --- React PWA (built into frontend/dist) -----------------------------------
DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"

if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

# Root-level PWA files the browser requests by fixed name.
PWA_FILES = {
    "/manifest.json": "application/manifest+json",
    "/sw.js": "application/javascript",
    "/icon-192.png": "image/png",
    "/icon-512.png": "image/png",
    "/favicon.svg": "image/svg+xml",
}


def _register_pwa_file(url_path: str, media_type: str) -> None:
    @app.get(url_path, include_in_schema=False)
    def serve_pwa_file():
        file = DIST_DIR / url_path.lstrip("/")
        if not file.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        headers = {"Cache-Control": "no-cache"} if url_path == "/sw.js" else None
        return FileResponse(file, media_type=media_type, headers=headers)


for _path, _type in PWA_FILES.items():
    _register_pwa_file(_path, _type)


@app.get("/healthz", include_in_schema=False)
def liveness():
    """Cheap liveness probe for container orchestrators (no dependency checks)."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def read_root():
    index = DIST_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"status": "running", "message": "MediQA Bot API is live"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))  # noqa: S104
