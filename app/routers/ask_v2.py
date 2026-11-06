"""POST /api/v2/ask: the v2 agent as a server-sent-events stream.

Events (each `event: <type>` + `data: <json>`): status, token, citations, done, error.
`done` carries the saved log `id` (use it with /api/v1/analytics/feedback), `safety`, `disclaimer`, `followups`.
Session list / history / delete / feedback are the existing /api/v1/analytics endpoints; history now includes `extra`.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from qdrant_client import models

from app.agent import v2
from app.config import settings
from app.core.cache import generate_cache_key, qa_cache
from app.core.rate_limiter import RateLimiter
from app.db import SessionLocal
from app.models import RAGQueryLog
from app.routers.analytics import analytics_rate_limiter
from app.schemas import AskRequest
from app.services.analytics_service import analytics_service
from app.services.search_v2 import COLLECTION

logger = logging.getLogger(__name__)
router = APIRouter()

qa_rate_limiter = RateLimiter(
    times=settings.RATE_LIMIT_QA_TIMES, seconds=settings.RATE_LIMIT_QA_SECONDS, namespace="qa_ask", enabled=settings.RATE_LIMIT_ENABLED
)

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


_topics: dict[str, list[str]] | None = None  # focus area -> its distinct MedQuAD questions, built once from Qdrant


def _topic_index() -> dict[str, list[str]]:
    global _topics
    if _topics is None:
        index: dict[str, set[str]] = {}
        offset = None
        only_questions = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="question"))])
        while True:
            points, offset = v2._search.client.scroll(COLLECTION, scroll_filter=only_questions, limit=1000, offset=offset,
                                                      with_payload=["focus_area", "question"], with_vectors=False)
            for p in points:
                if p.payload["focus_area"] != "General":  # MedQuAD's catch-all for rows with no topic: fragments, not a subject
                    index.setdefault(p.payload["focus_area"], set()).add(p.payload["question"])
            if offset is None:
                break
        _topics = {k: sorted(v) for k, v in index.items()}
    return _topics


@router.get("/topics", summary="Search health topics and their common questions", dependencies=[Depends(analytics_rate_limiter)])
async def topics(q: str = Query("", max_length=60), limit: int = Query(12, ge=1, le=30)):
    await v2.warmup()
    index = await asyncio.to_thread(_topic_index)
    q = " ".join(q.lower().split())
    if q:
        hits = sorted((t for t in index if q in t.lower()), key=lambda t: (not t.lower().startswith(q), t.lower()))
    else:
        hits = sorted(index, key=lambda t: (-len(index[t]), t.lower()))  # most-covered topics first
    return [{"topic": t, "questions": index[t][:8]} for t in hits[:limit]]
