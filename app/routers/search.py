import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.core.cache import generate_cache_key, search_cache
from app.core.rate_limiter import RateLimiter
from app.schemas import SearchRequest, SearchResponse
from app.services.search_service import search_engine

logger = logging.getLogger(__name__)
router = APIRouter()

search_rate_limiter = RateLimiter(
    times=settings.RATE_LIMIT_SEARCH_TIMES,
    seconds=settings.RATE_LIMIT_SEARCH_SECONDS,
    namespace="search",
    enabled=settings.RATE_LIMIT_ENABLED
)

@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Execute Hybrid Vector Search",
    dependencies=[Depends(search_rate_limiter)]
)
def search_knowledge_base(payload: SearchRequest):
    try:
        # Check In-Memory Cache (Zero Redis)
        cache_key = None
        if settings.CACHE_ENABLED:
            cache_key = generate_cache_key(query=payload.query, top_k=payload.top_k)
            cached_results = search_cache.get(cache_key)
            if cached_results is not None:
                return SearchResponse(
                    query=payload.query,
                    results_count=len(cached_results),
                    results=cached_results,
                    cached=True
                )

        results = search_engine.hybrid_search(query_text=payload.query, top_k=payload.top_k)
        
        # Store in In-Memory Cache
        if settings.CACHE_ENABLED and cache_key:
            search_cache.set(cache_key, results, ttl=settings.CACHE_SEARCH_TTL)

        return SearchResponse(
            query=payload.query,
            results_count=len(results),
            results=results,
            cached=False
        )
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("Search request failed")
        raise HTTPException(status_code=500, detail="Search failed. Please try again.") from None

