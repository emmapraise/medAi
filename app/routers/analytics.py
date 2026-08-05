from fastapi import APIRouter, HTTPException, Query
from app.services.analytics_service import analytics_service
from app.db import SessionLocal
from app.models import RAGQueryLog, ConversationSession

router = APIRouter()

@router.get("/summary", summary="Get RAG Performance & Cost Summary Metrics")
def get_performance_summary():
    try:
        return analytics_service.get_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs", summary="Get Paginated RAG Query Performance Logs")
def get_query_logs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    db = SessionLocal()
    try:
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
                "model_used": log.model_used,
                "latency_ms": log.latency_ms,
                "total_tokens": log.total_tokens,
                "estimated_cost_usd": log.estimated_cost_usd,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]
    finally:
        db.close()
