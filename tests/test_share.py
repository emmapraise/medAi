import pytest

import main
from app.services.analytics_service import analytics_service

CITES = [{"n": 1, "question": "What causes Glaucoma ?", "source": "NIH", "focus_area": "Glaucoma", "passage": "Pressure damages the nerve."}]


def seed(session_id="private-session-id", question="what causes glaucoma?", answer="Pressure [1]."):
    analytics_service.log_query(
        session_id=session_id, question=question, generated_query=question, retrieved_docs_count=1,
        is_relevant="yes", is_grounded="unknown", is_useful="unknown", turns_executed=1, execution_trace=["x"],
        answer=answer, model_used="gpt-4o-mini", latency_seconds=1.0, prompt_tokens=100, completion_tokens=20,
        extra={"citations": CITES, "followups": ["secret follow-up"], "safety": None, "abstained": False, "confidence": 0.93, "disclaimer": "d"},
    )


def share(client, session_id="private-session-id"):
    return client.post(f"/api/v2/sessions/{session_id}/share")


def test_only_an_existing_conversation_can_be_shared(client):
    assert share(client, "nothing-here").status_code == 404


def test_creating_a_link_is_repeatable_and_the_token_is_not_the_session_id(client):
    seed()
    first = share(client).json()["token"]
    assert first != "private-session-id" and len(first) >= 20
    assert share(client).json()["token"] == first  # the same link, not a new one each time
    assert client.get("/api/v2/sessions/private-session-id/share").json() == {"token": first}


def test_a_reader_gets_the_conversation_and_nothing_private(client):
    seed()
    token = share(client).json()["token"]
    r = client.get(f"/api/v2/shared/{token}")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]
    msg = r.json()["messages"][0]
    assert msg["question"] == "what causes glaucoma?" and msg["answer"] == "Pressure [1]."
    assert msg["extra"]["citations"][0]["passage"] == "Pressure damages the nerve."
    for private in ("private-session-id", "secret follow-up", "feedback", "token", "cost", "latency", "0.93", "model"):
        assert private not in r.text, private


def test_the_token_is_not_a_key_to_anything_else(client):
    seed()
    token = share(client).json()["token"]
    assert client.get(f"/api/v1/analytics/sessions/{token}").json()["messages"] == []  # it is not a session id
    assert client.get("/api/v2/shared/private-session-id-xx").status_code == 404  # and the session id is not a token


def test_stopping_kills_the_link_for_good_and_sharing_again_makes_a_new_one(client):
    seed()
    old = share(client).json()["token"]
    assert client.delete("/api/v2/sessions/private-session-id/share").json() == {"token": None}
    assert client.get(f"/api/v2/shared/{old}").status_code == 404
    new = share(client).json()["token"]
    assert new != old and client.get(f"/api/v2/shared/{old}").status_code == 404 and client.get(f"/api/v2/shared/{new}").status_code == 200


def test_deleting_the_conversation_kills_its_link(client):
    seed()
    token = share(client).json()["token"]
    assert client.delete("/api/v1/analytics/sessions/private-session-id").status_code == 200
    assert client.get(f"/api/v2/shared/{token}").status_code == 404


def test_bad_tokens_are_rejected(client):
    assert client.get("/api/v2/shared/x" * 1).status_code == 422  # too short to be a token
    assert client.get("/api/v2/shared/" + "a" * 22).status_code == 404  # well formed but unknown


def test_the_share_page_is_the_app_with_privacy_headers(client, tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<title>MediQA</title>")
    monkeypatch.setattr(main, "DIST_DIR", tmp_path)
    r = client.get("/s/" + "a" * 22)
    assert r.status_code == 200 and "<title>MediQA" in r.text
    assert "noindex" in r.headers["x-robots-tag"] and r.headers["referrer-policy"] == "no-referrer"
    monkeypatch.setattr(main, "DIST_DIR", tmp_path / "missing")
    assert client.get("/s/" + "a" * 22).status_code == 404


@pytest.mark.parametrize("method", ["get", "post", "delete"])
def test_session_ids_in_share_routes_are_validated(client, method):
    assert getattr(client, method)("/api/v2/sessions/bad%20id%21/share").status_code == 422
