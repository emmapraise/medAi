from app.core.cache import qa_cache
from app.db import SessionLocal
from app.models import ConversationSession, RAGQueryLog
from app.services.agent_service import agent_service


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
        ("post", "/api/v1/ingest"),
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


def test_ingest_rejects_paths_outside_dataset_dir(client, admin_headers):
    res = client.post("/api/v1/ingest", params={"dataset_path": "/etc/passwd"}, headers=admin_headers)
    assert res.status_code == 400
    res = client.post("/api/v1/ingest", params={"dataset_path": "dataset/../pyproject.toml"}, headers=admin_headers)
    assert res.status_code == 400


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
    assert client.post("/api/v1/ask", json={"question": "hi", "session_id": "a b!"}).status_code == 422


def test_delete_session_removes_rows(client):
    _seed_session("mine-1", "q")
    assert client.delete("/api/v1/analytics/sessions/mine-1").status_code == 200
    assert client.get("/api/v1/analytics/sessions", params={"ids": "mine-1"}).json() == []


# --- QA behaviour -------------------------------------------------------------
def _fake_result(answer: str) -> dict:
    return {
        "id": 1, "generated_query": "q", "answer": answer, "session_id": "s", "is_relevant": "yes",
        "is_grounded": "yes", "is_useful": "yes", "execution_trace": [], "latency_seconds": 0.1,
        "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "estimated_cost_usd": 0.0,
        "turns_executed": 1, "trace_id": None,
    }


def test_qa_cache_is_scoped_per_session(client, monkeypatch):
    """A follow-up like 'what are the treatments?' must not reuse another session's answer."""
    calls = []

    def fake_run_qa(question, session_id, model, max_turns):
        calls.append(session_id)
        return _fake_result(f"answer for {session_id}") | {"session_id": session_id}

    monkeypatch.setattr(agent_service, "run_qa", fake_run_qa)
    body = {"question": "What are the treatments?"}

    a = client.post("/api/v1/ask", json=body | {"session_id": "sess-a"}).json()
    b = client.post("/api/v1/ask", json=body | {"session_id": "sess-b"}).json()
    a_again = client.post("/api/v1/ask", json=body | {"session_id": "sess-a"}).json()

    assert a["answer"] == "answer for sess-a"
    assert b["answer"] == "answer for sess-b"
    assert a_again["cached"] is True
    assert calls == ["sess-a", "sess-b"]
    assert qa_cache.get_stats()["hits"] == 1


def test_errors_do_not_leak_internals(client, monkeypatch):
    def boom(**_):
        raise RuntimeError("secret connection string postgres://user:pw@host")

    monkeypatch.setattr(agent_service, "run_qa", boom)
    res = client.post("/api/v1/ask", json={"question": "hello", "session_id": "s1"})
    assert res.status_code == 500
    assert "postgres://" not in res.text


def test_feedback_value_is_validated(client):
    res = client.post("/api/v1/analytics/feedback", json={"log_id": 1, "feedback": "meh"})
    assert res.status_code == 422
