"""Read-only share links for a conversation, under /api/v2.

A conversation's id is a capability that also lets whoever holds it add to or delete the conversation, so it is never put
in a link. A link carries a separate random token that only allows reading, and that the owner can switch off again.
What a reader gets is the questions, the answers and their sources: no session id, no feedback, no token or cost figures.
"""
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ConversationSession, RAGQueryLog
from app.routers.analytics import analytics_rate_limiter

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
SessionId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Token = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{16,64}$")]


def _owned_session(db: Session, session_id: str) -> ConversationSession:
    row = db.get(ConversationSession, session_id)
    if not row or not db.query(RAGQueryLog.id).filter(RAGQueryLog.session_id == session_id).first():
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return row


@router.get("/sessions/{session_id}/share", summary="Is this conversation shared, and under which token?",
            dependencies=[Depends(analytics_rate_limiter)])
def share_status(session_id: SessionId, db: DbSession):
    row = db.get(ConversationSession, session_id)
    return {"token": row.share_id if row else None}


@router.post("/sessions/{session_id}/share", summary="Create the read-only link (the same one if it already exists)",
             dependencies=[Depends(analytics_rate_limiter)])
def start_sharing(session_id: SessionId, db: DbSession):
    row = _owned_session(db, session_id)
    if not row.share_id:
        row.share_id = secrets.token_urlsafe(16)  # 128 bits: not guessable
        db.commit()
    return {"token": row.share_id}


@router.delete("/sessions/{session_id}/share", summary="Stop sharing: the link stops working for good",
               dependencies=[Depends(analytics_rate_limiter)])
def stop_sharing(session_id: SessionId, db: DbSession):
    row = db.get(ConversationSession, session_id)
    if row and row.share_id:
        row.share_id = None  # a later share makes a new token, so the old link stays dead
        db.commit()
    return {"token": None}


@router.get("/shared/{token}", summary="Read a shared conversation (read only)", dependencies=[Depends(analytics_rate_limiter)])
def shared_conversation(token: Token, response: Response, db: DbSession):
    row = db.query(ConversationSession).filter(ConversationSession.share_id == token).first()
    if not row:
        raise HTTPException(status_code=404, detail="This link is not active.")
    logs = db.query(RAGQueryLog).filter(RAGQueryLog.session_id == row.session_id).order_by(RAGQueryLog.id.asc()).all()
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return {
        "messages": [
            {
                "id": i,
                "question": log.question,
                "answer": log.answer or "",
                "extra": {k: (log.extra or {}).get(k) for k in ("citations", "safety", "abstained")},
            }
            for i, log in enumerate(logs)
        ]
    }
