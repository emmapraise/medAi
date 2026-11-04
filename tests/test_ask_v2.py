import json

import pytest

from app.routers import ask_v2


def parse(body: str) -> list[dict]:
    out = []
    for block in body.strip().split("\n\n"):
        event, data = block.split("\n")
        out.append({"event": event.removeprefix("event: "), **json.loads(data.removeprefix("data: "))})
    return out


@pytest.fixture()
def fake_agent(monkeypatch):
    calls = []

    async def fake_run(question, history=None, plain=False):
        calls.append({"question": question, "history": history, "plain": plain})
        cites = [{"n": 1, "question": "What causes Glaucoma ?", "source": "NIH", "focus_area": "Glaucoma", "passage": "p"}]
        yield {"type": "status", "text": "Searching medical sources"}
        yield {"type": "token", "text": "Pressure damages the nerve [1]."}
        yield {"type": "citations", "items": cites}
        yield {"type": "done", "answer": "Pressure damages the nerve [1].", "latency_s": 1.0, "llm_calls": 1, "prompt_tokens": 100,
               "completion_tokens": 20, "citations": cites, "followups": ["Is it inherited?"], "abstained": False, "safety": None,
               "disclaimer": "d", "query": question, "confidence": 0.9}

    monkeypatch.setattr(ask_v2.v2, "run", fake_run)
    return calls


def test_stream_has_ordered_events_and_a_saved_log_id(client, fake_agent):
    r = client.post("/api/v2/ask", json={"question": "what causes glaucoma?", "session_id": "s1"})
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = parse(r.text)
    assert [e["event"] for e in evs] == ["status", "token", "citations", "done"]
    assert evs[-1]["id"] and evs[-1]["followups"] == ["Is it inherited?"]


def test_history_is_persisted_and_fed_to_the_next_turn(client, fake_agent):
    client.post("/api/v2/ask", json={"question": "what causes glaucoma?", "session_id": "s1"})
    client.post("/api/v2/ask", json={"question": "how is it treated?", "session_id": "s1"})
    assert fake_agent[1]["history"] == [{"role": "user", "content": "what causes glaucoma?"},
                                        {"role": "assistant", "content": "Pressure damages the nerve [1]."}]
    msgs = client.get("/api/v1/analytics/sessions/s1").json()["messages"]
    assert len(msgs) == 2 and msgs[0]["extra"]["citations"][0]["source"] == "NIH"


def test_repeat_first_turn_question_is_served_from_cache_without_the_agent(client, fake_agent):
    ask = lambda sid: parse(client.post("/api/v2/ask", json={"question": "What causes glaucoma?", "session_id": sid}).text)
    ask("a")
    again = ask("b")
    assert len(fake_agent) == 1
    assert again[-1]["cached"] is True and again[-1]["llm_calls"] == 0 and again[-1]["id"]


def test_follow_ups_are_never_cached(client, fake_agent):
    client.post("/api/v2/ask", json={"question": "hello there", "session_id": "s2"})
    client.post("/api/v2/ask", json={"question": "and treatment?", "session_id": "s2"})
    client.post("/api/v2/ask", json={"question": "and treatment?", "session_id": "s3"})  # first turn of a new session
    client.post("/api/v2/ask", json={"question": "and treatment?", "session_id": "s2"})  # follow-up again
    assert len(fake_agent) == 4  # the follow-ups never read or wrote the cache, so none of the four calls was skipped
    assert fake_agent[-1]["history"] and not fake_agent[2]["history"]


def test_bad_session_id_is_rejected(client, fake_agent):
    assert client.post("/api/v2/ask", json={"question": "hi", "session_id": "bad id!"}).status_code == 422


def test_topics_search_ranks_prefix_matches_first_and_lists_by_coverage_when_empty(client, monkeypatch):
    async def noop():
        return None
    monkeypatch.setattr(ask_v2.v2, "warmup", noop)
    monkeypatch.setattr(ask_v2, "_topics", {
        "Glaucoma": ["What causes Glaucoma ?", "What is (are) Glaucoma ?"],
        "Open-angle glaucoma": ["What is (are) Open-angle glaucoma ?"],
        "Asthma": ["a", "b", "c"],
    })
    names = lambda r: [t["topic"] for t in r.json()]
    assert names(client.get("/api/v2/topics?q=glau")) == ["Glaucoma", "Open-angle glaucoma"]
    assert names(client.get("/api/v2/topics")) == ["Asthma", "Glaucoma", "Open-angle glaucoma"]
    assert client.get("/api/v2/topics?q=zzz").json() == []
    assert client.get("/api/v2/topics?limit=99").status_code == 422


def test_general_catch_all_is_not_a_topic(monkeypatch):
    class Pt:
        def __init__(self, fa, q):
            self.payload = {"focus_area": fa, "question": q}

    class Client:
        def scroll(self, *a, **k):
            return [Pt("General", "What is?"), Pt("Asthma", "What causes Asthma ?")], None

    class Fake:
        client = Client()

    monkeypatch.setattr(ask_v2.v2, "_search", Fake())
    monkeypatch.setattr(ask_v2, "_topics", None)
    assert ask_v2._topic_index() == {"Asthma": ["What causes Asthma ?"]}


def test_plain_language_reaches_the_agent_and_has_its_own_cache_entry(client, fake_agent):
    ask = lambda level, sid: client.post("/api/v2/ask", json={"question": "What causes glaucoma?", "session_id": sid, "reading_level": level})
    ask("standard", "p1")
    ask("simple", "p2")   # same question, different level: must not be served the standard answer
    ask("simple", "p3")   # now it is cached
    assert [c["plain"] for c in fake_agent] == [False, True]
    assert client.post("/api/v2/ask", json={"question": "hi", "session_id": "p4", "reading_level": "expert"}).status_code == 422
