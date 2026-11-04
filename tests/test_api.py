from app.agent import v2
from app.db import SessionLocal
from app.models import ConversationSession, RAGQueryLog


def _seed_session(session_id: str, question: str) -> None:
    db = SessionLocal()
    try:
        db.add(ConversationSession(session_id=session_id, total_queries=1))
        db.flush()
        db.add(RAGQueryLog(session_id=session_id, question=question, answer="a", model_used="m"))
        db.commit()
    finally:
        db.close()


def test_liveness(client):
    assert client.get("/healthz").json() == {"status": "ok"}


# --- admin protection ---------------------------------------------------------
def test_admin_routes_require_api_key(client):
    for method, url in [
        ("get", "/api/v1/analytics/logs"),
        ("get", "/api/v1/analytics/cache/stats"),
        ("post", "/api/v1/analytics/cache/clear"),
    ]:
        assert getattr(client, method)(url).status_code == 401, url
        assert getattr(client, method)(url, headers={"X-API-Key": "wrong"}).status_code == 401, url


def test_admin_routes_accept_valid_key(client, admin_headers):
    assert client.get("/api/v1/analytics/logs", headers=admin_headers).status_code == 200
    assert client.post("/api/v1/analytics/cache/clear", headers=admin_headers).status_code == 200


def test_admin_locked_in_production_without_key(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_API_KEY", None)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert client.get("/api/v1/analytics/logs").status_code == 503


# --- session privacy ----------------------------------------------------------
def test_sessions_only_returns_requested_ids(client):
    _seed_session("mine-1", "my question")
    _seed_session("theirs-1", "someone else's question")

    assert client.get("/api/v1/analytics/sessions").json() == []
    rows = client.get("/api/v1/analytics/sessions", params={"ids": "mine-1"}).json()
    assert [r["session_id"] for r in rows] == ["mine-1"]
    assert rows[0]["preview"] == "my question"


def test_session_id_is_validated(client):
    assert client.get("/api/v1/analytics/sessions/bad%20id%21").status_code == 422
    assert client.post("/api/v2/ask", json={"question": "hi", "session_id": "a b!"}).status_code == 422


def test_delete_session_removes_rows(client):
    _seed_session("mine-1", "q")
    assert client.delete("/api/v1/analytics/sessions/mine-1").status_code == 200
    assert client.get("/api/v1/analytics/sessions", params={"ids": "mine-1"}).json() == []


# --- QA behaviour -------------------------------------------------------------
def test_errors_do_not_leak_internals(client, monkeypatch):
    class Broken:
        def search_with_confidence(self, q, k):
            raise RuntimeError("secret connection string postgres://user:pw@host")

    monkeypatch.setattr(v2, "_search", Broken())
    res = client.post("/api/v2/ask", json={"question": "what causes glaucoma?", "session_id": "s1"})
    assert res.status_code == 200  # the stream itself opened; the failure is an event inside it
    assert "event: error" in res.text and "Could not generate an answer" in res.text
    assert "postgres://" not in res.text and "RuntimeError" not in res.text


def test_health_reports_qdrant_state_from_the_v2_client(client, monkeypatch):
    class Client:
        def collection_exists(self, name):
            return True

        def get_collection(self, name):
            return type("Info", (), {"points_count": 47478})()

    monkeypatch.setattr(v2, "_search", type("S", (), {"client": Client()})())
    body = client.get("/api/v2/health").json()
    assert body["status"] == "healthy" and body["collection_exists"] and body["total_points"] == 47478
    monkeypatch.setattr(v2, "_search", None)
    assert client.get("/api/v2/health").json()["status"] == "unhealthy"


def test_feedback_value_is_validated(client):
    res = client.post("/api/v1/analytics/feedback", json={"log_id": 1, "feedback": "meh"})
    assert res.status_code == 422
