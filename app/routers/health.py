from fastapi import APIRouter
from app.config import settings
from app.schemas import HealthResponse
from app.services.search_service import search_engine

router = APIRouter()

@router.get("/health", response_model=HealthResponse, summary="Check API & Qdrant Status")
def health_check():
    qdrant_ok = False
    col_exists = False
    points_count = 0
    
    if search_engine.client:
        try:
            cols = [c.name for c in search_engine.client.get_collections().collections]
            qdrant_ok = True
            if settings.COLLECTION_NAME in cols:
                col_exists = True
                info = search_engine.client.get_collection(settings.COLLECTION_NAME)
                points_count = info.points_count or 0
        except Exception:
            pass

    return HealthResponse(
        status="healthy" if qdrant_ok else "unhealthy",
        qdrant_connected=qdrant_ok,
        qdrant_url=settings.QDRANT_URL,
        collection_exists=col_exists,
        total_points=points_count
    )
