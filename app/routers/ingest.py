import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.core.cache import clear_all_caches
from app.core.rate_limiter import RateLimiter
from app.core.security import require_admin
from app.schemas import IngestResponse
from app.services.search_service import search_engine

logger = logging.getLogger(__name__)
router = APIRouter()

ingest_rate_limiter = RateLimiter(
    times=settings.RATE_LIMIT_INGEST_TIMES,
    seconds=settings.RATE_LIMIT_INGEST_SECONDS,
    namespace="ingest",
    enabled=settings.RATE_LIMIT_ENABLED
)


def _resolve_dataset(dataset_path: str) -> Path:
    """Resolve a user-supplied path, refusing anything outside DATASET_DIR."""
    root = Path(settings.DATASET_DIR).resolve()
    candidate = Path(dataset_path).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=400, detail=f"Dataset must be inside '{settings.DATASET_DIR}/'.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Dataset file not found on server.")
    return candidate


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Trigger Dataset Ingestion (admin)",
    dependencies=[Depends(require_admin), Depends(ingest_rate_limiter)]
)
def trigger_ingestion(dataset_path: str = f"{settings.DATASET_DIR}/medquad.csv"):
    path = _resolve_dataset(dataset_path)
    try:
        count = search_engine.ingest_dataset(csv_path=str(path))
    except Exception:
        logger.exception("Ingestion failed")
        raise HTTPException(status_code=500, detail="Ingestion failed. See server logs.") from None
    # Invalidate search and QA caches when new data is indexed
    clear_all_caches()
    return IngestResponse(
        status="success",
        records_ingested=count,
        collection_name=settings.COLLECTION_NAME if search_engine.client else ""
    )
