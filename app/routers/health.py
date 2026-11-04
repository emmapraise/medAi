import logging

from fastapi import APIRouter, Depends

from app.agent import v2
from app.config import settings
from app.core.rate_limiter import RateLimiter
from app.schemas import HealthResponse
from app.services.search_v2 import COLLECTION, QDRANT_URL

logger = logging.getLogger(__name__)
router = APIRouter()

health_rate_limiter = RateLimiter(
    times=settings.RATE_LIMIT_HEALTH_TIMES,
    seconds=settings.RATE_LIMIT_HEALTH_SECONDS,
    namespace="health",
    enabled=settings.RATE_LIMIT_ENABLED
)


@router.get("/health", response_model=HealthResponse, summary="Check API & Qdrant status", dependencies=[Depends(health_rate_limiter)])
def health_check():
    connected = exists = False
    points = 0
    if v2._search:
        try:
            client = v2._search.client
            exists = client.collection_exists(COLLECTION)
            connected = True
            if exists:
                points = client.get_collection(COLLECTION).points_count or 0
        except Exception:
            logger.warning("Qdrant health probe failed", exc_info=True)
    return HealthResponse(
        status="healthy" if connected else "unhealthy",
        qdrant_connected=connected, qdrant_url=QDRANT_URL, collection_exists=exists, total_points=points,
    )
