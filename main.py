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
    search_engine.initialize()
    agent_service.initialize()
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

# Mount React PWA Dist Static Files
app.mount("/static", StaticFiles(directory="frontend/dist"), name="static")
app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

@app.get("/manifest.json")
def get_manifest():
    return FileResponse("frontend/dist/manifest.json")

@app.get("/sw.js")
def get_service_worker():
    return FileResponse("frontend/dist/sw.js", media_type="application/javascript")

@app.get("/icon-192.png")
def get_icon192():
    return FileResponse("frontend/dist/icon-192.png", media_type="image/svg+xml")

@app.get("/icon-512.png")
def get_icon512():
    return FileResponse("frontend/dist/icon-512.png", media_type="image/svg+xml")

@app.get("/", summary="Serve React PWA Frontend Dashboard")
def read_root():
    return FileResponse("frontend/dist/index.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
