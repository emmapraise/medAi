import datetime

from app.config import settings
from app.db import SessionLocal
from app.models import ConversationSession, RAGQueryLog
from app.services import hub
from app.services.hub_client import HubApiError

NOW = datetime.datetime(2026, 11, 4, 9, 30)  # naive UTC, like the database
YESTERDAY = datetime.datetime(2026, 11, 3, 14, 0)
PRIVATE_TEXT = "my private question about chest pain"


class FakeHub:
    def __init__(self, fail=None):
        self.metrics, self.emails, self.fail = [], [], fail

    def report_metrics(self, metrics):
        if self.fail == "metrics":
            raise HubApiError(401, "invalid_key", "nope")
        self.metrics += metrics
        return {"accepted": len(metrics)}

    def send_email(self, to, subject, **kw):
        self.emails.append({"to": to, "subject": subject, **kw})
        return {"id": "m1", "status": "simulated"}


def _seed():
    db = SessionLocal()
    db.add_all([ConversationSession(session_id="old", created_at=datetime.datetime(2026, 11, 1)), ConversationSession(session_id="new", created_at=YESTERDAY)])
    db.flush()
    db.add_all([
        RAGQueryLog(session_id="new", question=PRIVATE_TEXT, answer=PRIVATE_TEXT, model_used="gemini", estimated_cost_usd=0.25, user_feedback="positive", feedback_comment=PRIVATE_TEXT, created_at=YESTERDAY),
        RAGQueryLog(session_id="old", question=PRIVATE_TEXT, model_used="gemini", estimated_cost_usd=0.5, user_feedback="negative", created_at=YESTERDAY),
        RAGQueryLog(session_id="old", question="today", model_used="gemini", estimated_cost_usd=1, created_at=NOW),
    ])
    db.commit()
    db.close()


def test_day_counts_for_one_utc_day():
    _seed()
    db = SessionLocal()
    c = hub.day_counts(db, datetime.datetime(2026, 11, 3))
    db.close()
    assert c == {"users_total": 2, "users_new": 1, "users_active": 2, "requests": 2, "ai_cost_usd": 0.75, "feedback_up": 1, "feedback_down": 1}


def test_report_sends_standard_counts_and_never_user_text():
    _seed()
    fake = FakeHub()
    assert hub.report_metrics(days=2, now=NOW, client=fake) == {"sent": 10}
    assert {m["name"] for m in fake.metrics} == set(hub.METRICS)
    assert PRIVATE_TEXT not in repr(fake.metrics)
    yesterday = {m["name"]: m["value"] for m in fake.metrics if m["at"].day == 3}
    assert yesterday["requests"] == 2 and yesterday["users_new"] == 1


def test_report_skipped_without_hub_settings(monkeypatch):
    monkeypatch.setattr(settings, "HUB_KEY", None)
    assert hub.report_metrics() == {"skipped": True}
    assert hub.send_digest() == {"skipped": True}


def test_digest_email_goes_to_owner_once_per_day_with_numbers_only(monkeypatch):
    _seed()
    monkeypatch.setattr(settings, "REPORT_EMAIL", ["owner@example.com"])
    fake = FakeHub()
    assert hub.send_digest(now=NOW, client=fake) == {"status": "simulated"}
    (mail,) = fake.emails
    assert mail["to"] == ["owner@example.com"] and mail["idempotency_key"] == "mediqa-digest:2026-11-03"
    assert "Questions answered: 2" in mail["text"] and "$0.7500" in mail["text"]
    assert PRIVATE_TEXT not in repr(mail)


def test_one_failure_does_not_stop_the_other(monkeypatch):
    monkeypatch.setattr(settings, "HUB_URL", "http://hub.test")
    monkeypatch.setattr(settings, "HUB_KEY", "hk_test_x")
    monkeypatch.setattr(settings, "REPORT_EMAIL", ["owner@example.com"])
    fake = FakeHub(fail="metrics")
    monkeypatch.setattr(hub, "_client", lambda: fake)
    out = hub.run()
    assert out["metrics"] == {"error": "invalid_key"} and out["email"] == {"status": "simulated"}


def test_endpoint_is_admin_only(client, admin_headers, monkeypatch):
    assert client.post("/api/v1/analytics/hub/report").status_code == 401
    monkeypatch.setattr(settings, "HUB_KEY", None)
    r = client.post("/api/v1/analytics/hub/report", headers=admin_headers)
    assert r.status_code == 200 and r.json() == {"metrics": {"skipped": True}, "email": {"skipped": True}}
