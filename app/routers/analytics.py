import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import analytics_cache, clear_all_caches, get_all_cache_stats
from app.core.rate_limiter import RateLimiter
from app.core.security import require_admin
from app.db import get_db
from app.models import ConversationSession, RAGQueryLog
from app.schemas import AnalyticsFeedbackRequest, AnalyticsFeedbackResponse, CacheStatsResponse
from app.services.analytics_service import analytics_service

logger = logging.getLogger(__name__)
router = APIRouter()

analytics_rate_limiter = RateLimiter(
    times=settings.RATE_LIMIT_ANALYTICS_TIMES,
    seconds=settings.RATE_LIMIT_ANALYTICS_SECONDS,
    namespace="analytics",
    enabled=settings.RATE_LIMIT_ENABLED
)

DbSession = Annotated[Session, Depends(get_db)]
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


@router.get(
    "/summary",
    summary="Get RAG Performance & Cost Summary Metrics",
    dependencies=[Depends(analytics_rate_limiter)]
)
def get_performance_summary():
    try:
        cache_key = "analytics_summary"
        if settings.CACHE_ENABLED:
            cached_data = analytics_cache.get(cache_key)
            if cached_data is not None:
                return cached_data

        data = analytics_service.get_summary()
        if settings.CACHE_ENABLED:
            analytics_cache.set(cache_key, data, ttl=settings.CACHE_ANALYTICS_TTL)
        return data
    except Exception:
        logger.exception("Analytics summary failed")
        raise HTTPException(status_code=500, detail="Could not load analytics summary.") from None


@router.get(
    "/cache/stats",
    response_model=CacheStatsResponse,
    summary="Get In-Memory Cache Performance Statistics (admin)",
    dependencies=[Depends(require_admin), Depends(analytics_rate_limiter)]
)
def get_cache_statistics():
    return get_all_cache_stats()


@router.post(
    "/cache/clear",
    summary="Clear All In-Memory Caches (admin)",
    dependencies=[Depends(require_admin), Depends(analytics_rate_limiter)]
)
def clear_caches():
    clear_all_caches()
    return {"status": "success", "message": "All in-memory caches have been cleared"}


@router.post(
    "/feedback",
    response_model=AnalyticsFeedbackResponse,
    summary="Submit User Feedback (Thumbs Up / Down)",
    dependencies=[Depends(analytics_rate_limiter)]
)
def submit_feedback(payload: AnalyticsFeedbackRequest):
    try:
        success = analytics_service.record_feedback(payload.log_id, payload.feedback, payload.comment)
    except Exception:
        logger.exception("Recording feedback failed")
        raise HTTPException(status_code=500, detail="Could not record feedback.") from None
    if not success:
        raise HTTPException(status_code=404, detail="Query log record not found")
    return AnalyticsFeedbackResponse(status="success", log_id=payload.log_id, feedback=payload.feedback)


@router.get(
    "/logs",
    summary="Get Paginated RAG Query Performance Logs (admin)",
    dependencies=[Depends(require_admin), Depends(analytics_rate_limiter)]
)
def get_query_logs(db: DbSession, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    logs = db.query(RAGQueryLog).order_by(RAGQueryLog.id.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id": log.id,
            "session_id": log.session_id,
            "question": log.question,
            "generated_query": log.generated_query,
            "retrieved_docs_count": log.retrieved_docs_count,
            "is_relevant": log.is_relevant,
            "is_grounded": log.is_grounded,
            "is_useful": log.is_useful,
            "user_feedback": log.user_feedback,
            "feedback_comment": log.feedback_comment,
            "model_used": log.model_used,
            "latency_seconds": round(log.latency_seconds or 0.0, 2),
            "total_tokens": log.total_tokens,
            "estimated_cost_usd": log.estimated_cost_usd,
            "created_at": log.created_at.isoformat()
        }
        for log in logs
    ]


@router.get(
    "/sessions",
    summary="List the caller's own conversations",
    description="Session IDs act as private capabilities, so only the IDs the client "
                "already holds (`ids`, comma-separated) are ever returned.",
    dependencies=[Depends(analytics_rate_limiter)]
)
def get_sessions(db: DbSession, ids: str = Query("", max_length=4096)):
    wanted = [i for i in (p.strip() for p in ids.split(",")) if re.fullmatch(SESSION_ID_PATTERN, i)][:50]
    if not wanted:
        return []

    first_ids = (
        db.query(func.min(RAGQueryLog.id).label("first_id"))
        .filter(RAGQueryLog.session_id.in_(wanted))
        .group_by(RAGQueryLog.session_id)
        .subquery()
    )
    previews = {
        row.session_id: row.question
        for row in db.query(RAGQueryLog.session_id, RAGQueryLog.question)
        .filter(RAGQueryLog.id.in_(db.query(first_ids.c.first_id)))
    }
    sessions = (
        db.query(ConversationSession)
        .filter(ConversationSession.session_id.in_(wanted))
        .order_by(ConversationSession.last_active_at.desc())
        .all()
    )
    return [
        {
            "session_id": s.session_id,
            "created_at": s.created_at.isoformat(),
            "last_active_at": s.last_active_at.isoformat(),
            "total_queries": s.total_queries,
            "preview": previews.get(s.session_id, "Empty conversation"),
        }
        for s in sessions
    ]


SessionIdPath = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]


@router.get(
    "/sessions/{session_id}",
    summary="Get Full Chat History for a Specific Session",
    dependencies=[Depends(analytics_rate_limiter)]
)
def get_session_history(session_id: SessionIdPath, db: DbSession):
    logs = db.query(RAGQueryLog).filter(RAGQueryLog.session_id == session_id).order_by(RAGQueryLog.id.asc()).all()
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": log.id,
                "question": log.question,
                "generated_query": log.generated_query or "",
                "answer": log.answer or "",
                "is_relevant": log.is_relevant or "unknown",
                "is_grounded": log.is_grounded or "unknown",
                "is_useful": log.is_useful or "unknown",
                "execution_trace": log.execution_trace or [],
                "user_feedback": log.user_feedback,
                "feedback_comment": log.feedback_comment,
                "latency_seconds": round(log.latency_seconds or 0.0, 2),
                "total_tokens": log.total_tokens or 0,
                "estimated_cost_usd": log.estimated_cost_usd or 0.0,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    }


@router.delete(
    "/sessions/{session_id}",
    summary="Delete All Logs for a Specific Session",
    dependencies=[Depends(analytics_rate_limiter)]
)
def delete_session(session_id: SessionIdPath, db: DbSession):
    try:
        deleted_count = db.query(RAGQueryLog).filter(RAGQueryLog.session_id == session_id).delete()
        db.query(ConversationSession).filter(ConversationSession.session_id == session_id).delete()
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Deleting session failed")
        raise HTTPException(status_code=500, detail="Could not delete the conversation.") from None
    return {"session_id": session_id, "deleted_count": deleted_count, "status": "success"}
