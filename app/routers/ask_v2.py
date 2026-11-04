"""POST /api/v2/ask: the v2 agent as a server-sent-events stream.

Events (each `event: <type>` + `data: <json>`): status, token, citations, done, error.
`done` carries the saved log `id` (use it with /api/v1/analytics/feedback), `safety`, `disclaimer`, `followups`.
Session list / history / delete / feedback are the existing /api/v1/analytics endpoints; history now includes `extra`.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent import v2
from app.config import settings
from app.core.cache import generate_cache_key, qa_cache
from app.db import SessionLocal
from app.models import RAGQueryLog
from app.routers.qa import qa_rate_limiter
from app.schemas import AskRequest
from app.services.analytics_service import analytics_service

logger = logging.getLogger(__name__)
router = APIRouter()

HISTORY_TURNS = 3


def _history(session_id: str) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(RAGQueryLog).filter(RAGQueryLog.session_id == session_id).order_by(RAGQueryLog.id.desc()).limit(HISTORY_TURNS).all()
    except Exception:
        logger.warning("History lookup failed; continuing without it", exc_info=True)
        return []
    finally:
        db.close()
    return [m for r in reversed(rows) if r.question and r.answer
            for m in ({"role": "user", "content": r.question}, {"role": "assistant", "content": r.answer})]


def _save(session_id: str, question: str, ev: dict) -> dict:
    if ev["safety"]:
        trace = [f"Safety gate: {ev['safety']}"]
    else:
        trace = [f"Searched medical sources (confidence {ev.get('confidence')})", f"{ev['llm_calls']} LLM call(s)"]
    row = analytics_service.log_query(
        session_id=session_id, question=question, generated_query=ev.get("query") or question,
        retrieved_docs_count=len(ev["citations"]),
        is_relevant="no" if ev["abstained"] else "yes", is_grounded="unknown", is_useful="unknown",
        turns_executed=ev["llm_calls"], execution_trace=trace, answer=ev["answer"],
        model_used=v2.OPENAI_MODEL if v2.PROVIDER == "openai" else settings.DEFAULT_MODEL,
        latency_seconds=ev["latency_s"], prompt_tokens=ev["prompt_tokens"], completion_tokens=ev["completion_tokens"],
        extra={k: ev.get(k) for k in ("citations", "followups", "safety", "disclaimer", "abstained", "confidence")},
    )
    return {**ev, "id": row.id}


async def _replay(done: dict):
    yield {"type": "token", "text": done["answer"]}
    yield {"type": "citations", "items": done["citations"]}
    yield {**done, "cached": True, "llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "latency_s": 0.0}


def _sse(ev: dict) -> str:
    return f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"


async def _stream(payload: AskRequest):
    sid, question = payload.session_id, payload.question
    history = await asyncio.to_thread(_history, sid)
    # Only first-turn questions are cached: a follow-up's meaning depends on the conversation.
    key = None if history or not settings.CACHE_ENABLED else generate_cache_key(v="v2", question=" ".join(question.lower().split()))
    cached = qa_cache.get(key) if key else None
    async for ev in (_replay(cached) if cached else v2.run(question, history)):
        if ev["type"] == "done":
            ev = await asyncio.to_thread(_save, sid, question, ev)
            if key and not cached and ev["llm_calls"] and not ev["abstained"] and not ev["safety"]:
                qa_cache.set(key, {k: v for k, v in ev.items() if k != "id"}, ttl=settings.CACHE_QA_TTL)
        yield _sse(ev)


@router.post("/ask", summary="Ask the v2 medical agent (SSE stream)", dependencies=[Depends(qa_rate_limiter)])
async def ask_v2(payload: AskRequest):
    return StreamingResponse(_stream(payload), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
