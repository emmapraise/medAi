"""Reports daily COUNTS to Admin Hub and emails the owner a daily summary through it.

Counts only: never questions, answers, feedback comments or any other user text.
MediQA has no accounts, so a "user" here is a visitor session: users_total = sessions ever, users_new = sessions started that day,
users_active = sessions that asked something that day. requests = questions answered; ai_cost_usd = estimated model spend.
Each day is one point per metric (stamped at the start of the UTC day), so re-running overwrites it and is safe to retry.
"""
import datetime
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import ConversationSession, RAGQueryLog
from app.services.hub_client import HubApiError, HubClient

logger = logging.getLogger(__name__)

DAY = datetime.timedelta(days=1)


def _client() -> HubClient | None:
    return HubClient(settings.HUB_URL, settings.HUB_KEY) if settings.HUB_URL and settings.HUB_KEY else None


def day_counts(db: Session, start: datetime.datetime) -> dict[str, float]:
    """Counts for the UTC day [start, start + 1 day). Timestamps in the database are naive UTC."""
    end = start + DAY
    in_day = lambda col: (col >= start) & (col < end)  # noqa: E731
    asked = db.query(func.count(RAGQueryLog.id), func.count(func.distinct(RAGQueryLog.session_id)), func.coalesce(func.sum(RAGQueryLog.estimated_cost_usd), 0.0)).filter(in_day(RAGQueryLog.created_at)).one()
    return {
        "users_total": db.query(func.count(ConversationSession.session_id)).filter(ConversationSession.created_at < end).scalar() or 0,
        "users_new": db.query(func.count(ConversationSession.session_id)).filter(in_day(ConversationSession.created_at)).scalar() or 0,
        "users_active": asked[1],
        "requests": asked[0],
        "ai_cost_usd": round(float(asked[2]), 6),
        "feedback_up": db.query(func.count(RAGQueryLog.id)).filter(in_day(RAGQueryLog.created_at), RAGQueryLog.user_feedback == "positive").scalar() or 0,
        "feedback_down": db.query(func.count(RAGQueryLog.id)).filter(in_day(RAGQueryLog.created_at), RAGQueryLog.user_feedback == "negative").scalar() or 0,
    }


# Only these names are sent as metrics (the hub's standard names); feedback counts are for the email.
METRICS = ("users_total", "users_new", "users_active", "requests", "ai_cost_usd")


def _today(now: datetime.datetime | None) -> datetime.datetime:
    n = now or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def report_metrics(days: int = 2, now: datetime.datetime | None = None, client: HubClient | None = None) -> dict:
    """Sends the last `days` UTC days (today is partial and gets overwritten on the next run)."""
    client = client or _client()
    if client is None:
        return {"skipped": True}
    today, days = _today(now), min(max(days, 1), 90)
    db = SessionLocal()
    try:
        metrics = []
        for i in range(days):
            start = today - i * DAY
            counts = day_counts(db, start)
            metrics += [{"name": n, "value": counts[n], "at": start.replace(tzinfo=datetime.UTC)} for n in METRICS]
    finally:
        db.close()
    return {"sent": client.report_metrics(metrics)["accepted"]}


def digest(counts: dict[str, float], day: datetime.date) -> tuple[str, str]:
    """Subject and plain-text body. Numbers only."""
    lines = [
        f"MediQA on {day.isoformat()} (UTC)",
        "",
        f"Questions answered: {counts['requests']:g}",
        f"Visitors who asked: {counts['users_active']:g} ({counts['users_new']:g} new)",
        f"Estimated AI cost: ${counts['ai_cost_usd']:.4f}",
        f"Feedback: {counts['feedback_up']:g} helpful, {counts['feedback_down']:g} not helpful",
        f"Visitors so far: {counts['users_total']:g}",
    ]
    return f"MediQA daily summary, {day.isoformat()}", "\n".join(lines)


def send_digest(now: datetime.datetime | None = None, client: HubClient | None = None) -> dict:
    """Emails yesterday's (complete) numbers to REPORT_EMAIL through the hub. Sending twice for a day sends once (idempotency key)."""
    client = client or _client()
    if client is None or not settings.REPORT_EMAIL:
        return {"skipped": True}
    start = _today(now) - DAY
    db = SessionLocal()
    try:
        counts = day_counts(db, start)
    finally:
        db.close()
    subject, text = digest(counts, start.date())
    res = client.send_email(settings.REPORT_EMAIL, subject, text=text, from_name="MediQA", idempotency_key=f"mediqa-digest:{start.date().isoformat()}")
    return {"status": res.get("status", "sent")}


def run(days: int = 2) -> dict:
    """What the daily scheduler calls: metrics, then the email. A hub failure on one does not stop the other."""
    out: dict = {}
    for name, fn in (("metrics", lambda: report_metrics(days)), ("email", send_digest)):
        try:
            out[name] = fn()
        except HubApiError as e:
            logger.warning("Hub %s failed: status=%s code=%s", name, e.status, e.code)  # codes only, never message text
            out[name] = {"error": e.code}
        except OSError as e:
            logger.warning("Hub %s unreachable: %s", name, type(e).__name__)
            out[name] = {"error": "unreachable"}
    return out
