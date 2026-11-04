import asyncio

from app.agent import v2


def collect(coro_gen):
    async def go():
        return [ev async for ev in coro_gen]
    return asyncio.run(go())


def test_splitter_hides_followups_even_when_marker_is_split_across_chunks():
    s = v2.Splitter()
    shown = "".join(s.feed(c) for c in ["Glaucoma damages the nerve [1].\n===FOLL", "OWUPS===\n1. Is it inherited?\n- How is it treated?\n"])
    rest, followups = s.finish()
    assert (shown + rest).strip() == "Glaucoma damages the nerve [1]."
    assert followups == ["Is it inherited?", "How is it treated?"]


def test_splitter_without_marker_loses_no_text():
    s = v2.Splitter()
    shown = "".join(s.feed(c) for c in ["Hello ", "wor", "ld"])
    rest, followups = s.finish()
    assert shown + rest == "Hello world" and followups == []


def test_low_confidence_abstains_without_calling_the_llm(monkeypatch):
    class Fake:
        def search_with_confidence(self, q, k):
            return [{"question": "q", "source": "S", "focus_area": "f", "chunk": "c"}], 0.5

    async def boom(*a, **k):
        raise AssertionError("LLM must not be called")
        yield
    monkeypatch.setattr(v2, "_search", Fake())
    monkeypatch.setattr(v2, "_stream_llm", boom)
    evs = collect(v2.run("best pizza in Lagos"))
    assert evs[-1]["type"] == "done" and evs[-1]["abstained"] and evs[-1]["llm_calls"] == 0


def test_answer_streams_one_llm_call_and_returns_only_cited_sources(monkeypatch):
    class Fake:
        def search_with_confidence(self, q, k):
            d = lambda n: {"question": f"Q{n}", "source": "GARD", "focus_area": "Glaucoma", "chunk": f"passage {n}"}
            return [d(1), d(2)], 0.9

    async def fake_llm(prompt, history, plain=False):
        yield "Glaucoma harms the optic nerve [2].\n===FOLLOWUPS===\nIs it inherited?\n", None
        yield "", (100, 20)
    monkeypatch.setattr(v2, "_search", Fake())
    monkeypatch.setattr(v2, "_stream_llm", fake_llm)
    evs = collect(v2.run("what is glaucoma"))
    final = evs[-1]
    assert final["llm_calls"] == 1 and final["prompt_tokens"] == 100 and not final["abstained"]
    assert [c["n"] for c in final["citations"]] == [2] and final["followups"] == ["Is it inherited?"]
    assert "FOLLOWUPS" not in "".join(e["text"] for e in evs if e["type"] == "token")


def test_greeting_needs_no_search_and_no_llm():
    final = collect(v2.run("hello!"))[-1]
    assert final["llm_calls"] == 0 and final["answer"] == v2.GREETING_REPLY


def test_emergency_gets_fixed_reply_with_no_search_and_no_llm(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("LLM must not be called")
        yield
    monkeypatch.setattr(v2, "_search", None)
    monkeypatch.setattr(v2, "_stream_llm", boom)
    final = collect(v2.run("I have crushing chest pain spreading to my left arm"))[-1]
    assert final["safety"] == "emergency" and final["llm_calls"] == 0 and "emergency number" in final["answer"]
    assert final["disclaimer"]


def test_plain_language_adds_a_reading_level_rule_only_when_asked():
    assert "6th-grade" in v2._system(True) and "6th-grade" not in v2._system(False)
    assert "{extra}" not in v2._system(True) and "{extra}" not in v2._system(False)
    assert v2._system(True).rstrip().endswith("no numbering.")  # the follow-up instruction is still last
