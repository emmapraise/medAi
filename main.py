import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.services.search_service import search_engine
from app.services.agent_service import agent_service
from app.routers import health, search, qa, ingest, analytics

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Medical QA Server & React PWA Application...")
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, search_engine.initialize)
    loop.run_in_executor(None, agent_service.initialize)
    yield
    print("Shutting down Medical QA Server...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A Production-Ready Medical QA API & React PWA Application with LangGraph CRAG & PostgreSQL Analytics.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(search.router, prefix="/api/v1", tags=["Search"])
app.include_router(qa.router, prefix="/api/v1", tags=["QA Agent"])
app.include_router(ingest.router, prefix="/api/v1", tags=["Ingestion"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics & Cost Monitoring"])

# Mount React PWA Dist Static Files if available
if os.path.exists("frontend/dist"):
    app.mount("/static", StaticFiles(directory="frontend/dist", check_dir=False), name="static")
    if os.path.exists("frontend/dist/assets"):
        app.mount("/assets", StaticFiles(directory="frontend/dist/assets", check_dir=False), name="assets")

@app.get("/manifest.json")
def get_manifest():
    if os.path.exists("frontend/dist/manifest.json"):
        return FileResponse("frontend/dist/manifest.json")
    return {"status": "ok"}

@app.get("/sw.js")
def get_service_worker():
    if os.path.exists("frontend/dist/sw.js"):
        return FileResponse("frontend/dist/sw.js", media_type="application/javascript")
    return {"status": "ok"}

@app.get("/icon-192.png")
def get_icon192():
    if os.path.exists("frontend/dist/icon-192.png"):
        return FileResponse("frontend/dist/icon-192.png", media_type="image/png")
    return {"status": "ok"}

@app.get("/icon-512.png")
def get_icon512():
    if os.path.exists("frontend/dist/icon-512.png"):
        return FileResponse("frontend/dist/icon-512.png", media_type="image/png")
    return {"status": "ok"}

@app.get("/", summary="Serve React PWA Frontend Dashboard")
def read_root():
    if os.path.exists("frontend/dist/index.html"):
        return FileResponse("frontend/dist/index.html")
    return {"status": "running", "message": "MediQA Bot API is live"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
