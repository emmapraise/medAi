import logging

from fastapi import APIRouter, Depends, HTTPException
from langfuse import get_client

from app.config import settings
from app.core.cache import generate_cache_key, qa_cache
from app.core.rate_limiter import RateLimiter
from app.schemas import AskRequest, AskResponse, FeedbackRequest, FeedbackResponse
from app.services.agent_service import agent_service

logger = logging.getLogger(__name__)
router = APIRouter()

qa_rate_limiter = RateLimiter(
    times=settings.RATE_LIMIT_QA_TIMES,
    seconds=settings.RATE_LIMIT_QA_SECONDS,
    namespace="qa_ask",
    enabled=settings.RATE_LIMIT_ENABLED
)

feedback_rate_limiter = RateLimiter(
    times=settings.RATE_LIMIT_ANALYTICS_TIMES,
    seconds=settings.RATE_LIMIT_ANALYTICS_SECONDS,
    namespace="qa_feedback",
    enabled=settings.RATE_LIMIT_ENABLED
)

@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask AI Medical Agent (LangGraph CRAG + Follow-up Memory)",
    dependencies=[Depends(qa_rate_limiter)]
)
def ask_medical_agent(payload: AskRequest):
    try:
        session = payload.session_id or "default_session"
        model_name = payload.model or settings.DEFAULT_MODEL
        
        # Check In-Memory Cache (Zero Redis)
        cache_key = None
        if settings.CACHE_ENABLED:
            cache_key = generate_cache_key(
                question=payload.question,
                session_id=session,  # follow-ups ("what about treatment?") depend on history
                model=model_name,
                max_turns=payload.max_turns or 5
            )
            cached_result = qa_cache.get(cache_key)
            if cached_result is not None:
                cached_copy = dict(cached_result)
                cached_copy["cached"] = True
                return AskResponse(**cached_copy)

        result = agent_service.run_qa(
            question=payload.question,
            session_id=session,
            model=model_name,
            max_turns=payload.max_turns or 5
        )
        
        response_data = {
            "id": result.get("id"),
            "question": payload.question,
            "generated_query": result["generated_query"],
            "answer": result["answer"],
            "session_id": result["session_id"],
            "is_relevant": result["is_relevant"],
            "is_grounded": result["is_grounded"],
            "is_useful": result["is_useful"],
            "execution_trace": result["execution_trace"],
            "model_used": model_name,
            "latency_seconds": result["latency_seconds"],
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "total_tokens": result["total_tokens"],
            "estimated_cost_usd": result["estimated_cost_usd"],
            "turns_executed": result["turns_executed"],
            "trace_id": result.get("trace_id"),
            "cached": False
        }

        # Store in In-Memory Cache
        if settings.CACHE_ENABLED and cache_key:
            qa_cache.set(cache_key, response_data, ttl=settings.CACHE_QA_TTL)

        return AskResponse(**response_data)
    except HTTPException as he:
        raise he
    except Exception:
        logger.exception("QA request failed")
        raise HTTPException(status_code=500, detail="Could not generate an answer. Please try again.") from None

@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Submit User Thumbs/Rating Score to Langfuse Trace",
    dependencies=[Depends(feedback_rate_limiter)]
)
def submit_feedback(payload: FeedbackRequest):
    try:
        score_name = payload.name or "user-feedback"
        lf = get_client()
        lf.create_score(
            trace_id=payload.trace_id,
            name=score_name,
            value=float(payload.value),
            data_type="NUMERIC" if payload.value not in (0.0, 1.0) else "BOOLEAN",
            comment=payload.comment
        )
        return FeedbackResponse(
            status="success",
            trace_id=payload.trace_id,
            name=score_name,
            value=float(payload.value)
        )
    except Exception:
        logger.exception("Langfuse feedback failed")
        raise HTTPException(status_code=500, detail="Could not record feedback.") from None

