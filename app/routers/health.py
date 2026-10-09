import logging

from fastapi import APIRouter, Depends

from app.config import settings
from app.core.rate_limiter import RateLimiter
from app.schemas import HealthResponse
from app.services.search_service import search_engine

logger = logging.getLogger(__name__)
router = APIRouter()

health_rate_limiter = RateLimiter(
    times=settings.RATE_LIMIT_HEALTH_TIMES,
    seconds=settings.RATE_LIMIT_HEALTH_SECONDS,
    namespace="health",
    enabled=settings.RATE_LIMIT_ENABLED
)

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check API & Qdrant Status",
    dependencies=[Depends(health_rate_limiter)]
)
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
            logger.warning("Qdrant health probe failed", exc_info=True)

    return HealthResponse(
        status="healthy" if qdrant_ok else "unhealthy",
        qdrant_connected=qdrant_ok,
        qdrant_url=settings.QDRANT_URL,
        collection_exists=col_exists,
        total_points=points_count
    )

