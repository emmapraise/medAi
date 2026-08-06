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
                "latency_seconds": round(getattr(log, "latency_seconds", 0.0), 2),
                "total_tokens": log.total_tokens,
                "estimated_cost_usd": log.estimated_cost_usd,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]
    finally:
        db.close()

@router.get("/sessions", summary="Get List of Past Conversation Sessions")
def get_sessions(limit: int = Query(20, ge=1, le=50)):
    db = SessionLocal()
    try:
        sessions = db.query(ConversationSession).order_by(ConversationSession.last_active_at.desc()).limit(limit).all()
        result = []
        for s in sessions:
            first_log = db.query(RAGQueryLog).filter(RAGQueryLog.session_id == s.session_id).order_by(RAGQueryLog.id.asc()).first()
            result.append({
                "session_id": s.session_id,
                "created_at": s.created_at.isoformat(),
                "last_active_at": s.last_active_at.isoformat(),
                "total_queries": s.total_queries,
                "total_tokens": s.total_tokens,
                "total_cost_usd": s.total_cost_usd,
                "preview": first_log.question if first_log else "Empty Session"
            })
        return result
    finally:
        db.close()

@router.get("/sessions/{session_id}", summary="Get Full Chat History for a Specific Session")
def get_session_history(session_id: str):
    db = SessionLocal()
    try:
        logs = db.query(RAGQueryLog).filter(RAGQueryLog.session_id == session_id).order_by(RAGQueryLog.id.asc()).all()
        return {
            "session_id": session_id,
            "messages": [
                {
                    "id": log.id,
                    "question": log.question,
                    "generated_query": log.generated_query,
                    "answer": log.answer,
                    "is_relevant": log.is_relevant,
                    "is_grounded": log.is_grounded,
                    "is_useful": log.is_useful,
                    "execution_trace": log.execution_trace or [],
                    "latency_seconds": round(getattr(log, "latency_seconds", 0.0), 2),
                    "total_tokens": log.total_tokens,
                    "estimated_cost_usd": log.estimated_cost_usd,
                    "created_at": log.created_at.isoformat()
                }
                for log in logs
            ]
        }
    finally:
        db.close()

@router.delete("/sessions/{session_id}", summary="Delete All Logs for a Specific Session")
def delete_session(session_id: str):
    db = SessionLocal()
    try:
        deleted_count = db.query(RAGQueryLog).filter(RAGQueryLog.session_id == session_id).delete()
        db.commit()
        return {"session_id": session_id, "deleted_count": deleted_count, "status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
