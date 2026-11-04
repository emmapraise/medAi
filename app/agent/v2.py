"""v2 agent: retrieve -> (abstain | ONE streamed LLM call). No LangGraph, no LLM graders.

LLM calls per question: 1 (first turn) or 2 (follow-up that needs history to become a standalone query).
Groundedness is no longer judged per request; it is an offline eval metric.

    async for ev in run("what causes glaucoma?"): ...
Events: status {text} | token {text} | citations {items} | done {...} | error {message}
"""
import asyncio
import os
import re
import time
from collections.abc import AsyncIterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from openai import AsyncOpenAI

from app.config import settings
from app.services.search_v2 import SearchV2

MIN_DENSE = float(os.getenv("V2_MIN_DENSE", "0.65"))  # calibrated on eval/cases.jsonl: in-corpus >= 0.80, off-topic <= 0.646
TOP_K = 4
PROVIDER = os.getenv("V2_LLM", "openai" if settings.OPENAI_API_KEY else "gemini")
OPENAI_MODEL = os.getenv("V2_OPENAI_MODEL", "gpt-4o-mini")
MARK = "===FOLLOWUPS==="

GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|thanks?|thank you|bye|goodbye)\b[\s!.,?]*$", re.I)
GREETING_REPLY = "Hello, I'm MediQA. Ask me a health question and I'll answer from NIH-sourced medical information."
NOT_FOUND = ("I couldn't find this in the NIH health sources I search (MedQuAD), so I won't guess. "
             "Try rephrasing, or ask a doctor or pharmacist.")

SYSTEM = f"""You are MediQA, a medical information assistant. Answer ONLY from the numbered sources.
- Cite sources inline like [1] or [2][3] right after the claim they support.
- If the sources do not answer the question, say so briefly. Never guess.
- If the question names no specific condition or topic (e.g. 'what causes it?') or the sources cover unrelated conditions, do not answer: ask which condition the user means, with no citations.
- Plain, calm language. No diagnosis and no personal dosing advice; suggest seeing a clinician when relevant.
- After the answer, write a line containing exactly {MARK} then 3 short follow-up questions the user might ask next, one per line, no numbering."""

_search: SearchV2 | None = None
_client: genai.Client | None = None
_oa: AsyncOpenAI | None = None


class Splitter:
    """Streams answer text while hiding the follow-up block that starts at MARK, even if MARK arrives split across chunks."""

    def __init__(self):
        self.buf, self.tail, self.found = "", "", False

    def feed(self, text: str) -> str:
        if self.found:
            self.tail += text
            return ""
        self.buf += text
        i = self.buf.find(MARK)
        if i >= 0:
            out, self.tail, self.buf, self.found = self.buf[:i], self.buf[i + len(MARK):], "", True
            return out
        hold = len(MARK) - 1  # a prefix of MARK may be sitting at the end of buf
        out, self.buf = self.buf[:-hold], self.buf[-hold:]
        return out

    def finish(self) -> tuple[str, list[str]]:
        followups = [re.sub(r"^[\s\-*•\d.)]+", "", ln).strip() for ln in self.tail.splitlines()]
        return self.buf, [f for f in followups if f][:3]


def _prompt(question: str, docs: list[dict]) -> str:
    src = "\n\n".join(f"[{i}] ({d['source']} · {d['focus_area']}) {d['question']}\n{d['chunk']}" for i, d in enumerate(docs, 1))
    return f"Sources:\n{src}\n\nQuestion: {question}"


def _cited(text: str, docs: list[dict]) -> list[dict]:
    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text) if 0 < int(n) <= len(docs)})
    return [{"n": n, "question": docs[n - 1]["question"], "source": docs[n - 1]["source"], "focus_area": docs[n - 1]["focus_area"],
             "passage": docs[n - 1]["chunk"]} for n in used]


def _messages(history: list[dict], last: str, n: int, clip: int) -> list[dict]:
    return [{"role": h["role"], "content": h["content"][:clip]} for h in history[-n:]] + [{"role": "user", "content": last}]


def _openai() -> AsyncOpenAI:
    global _oa
    _oa = _oa or AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=30)  # the SDK itself retries 429/5xx twice
    return _oa


def _gemini() -> genai.Client:
    global _client
    _client = _client or genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


async def _resolve(question: str, history: list[dict]) -> tuple[str, int, int]:
    """Standalone search query from the chat history. One small non-streaming call."""
    ask = ("Rewrite the user's last message as one standalone medical search query "
           "(resolve 'it', 'yes', 'tell me more' from the conversation). Output only the query.")
    msgs = _messages(history, f"{question}\n\n{ask}", 6, 600)
    if PROVIDER == "openai":
        r = await _openai().chat.completions.create(model=OPENAI_MODEL, messages=msgs, temperature=0, max_tokens=60)
        text, p, c = r.choices[0].message.content or "", r.usage.prompt_tokens, r.usage.completion_tokens
    else:
        hist = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
        r = await _gemini().aio.models.generate_content(
            model=settings.DEFAULT_MODEL, contents=hist,
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=60, thinking_config=types.ThinkingConfig(thinking_budget=0)))
        text, p, c = r.text or "", r.usage_metadata.prompt_token_count or 0, r.usage_metadata.candidates_token_count or 0
    return text.strip().strip("\"'").split("\n")[0] or question, p, c


async def _stream_llm(prompt: str, history: list[dict]) -> AsyncIterator[tuple[str, tuple[int, int] | None]]:
    """Yields (text, None) per chunk, then ("", (prompt_tokens, completion_tokens)) at the end."""
    msgs = _messages(history, prompt, 4, 1500)
    if PROVIDER == "openai":
        stream = await _openai().chat.completions.create(
            model=OPENAI_MODEL, messages=[{"role": "system", "content": SYSTEM}, *msgs], temperature=0.3, max_tokens=900,
            stream=True, stream_options={"include_usage": True})
        usage = (0, 0)
        async for ch in stream:
            if ch.usage:
                usage = (ch.usage.prompt_tokens, ch.usage.completion_tokens)
            if ch.choices and ch.choices[0].delta.content:
                yield ch.choices[0].delta.content, None
        yield "", usage
        return
    contents = [types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])]) for m in msgs]
    usage, started = (0, 0), False
    for attempt in range(3):  # Gemini answers 503 "high demand" in bursts; retry only before any text was sent
        try:
            stream = await _gemini().aio.models.generate_content_stream(
                model=settings.DEFAULT_MODEL, contents=contents,
                config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.3, max_output_tokens=900,
                                                   thinking_config=types.ThinkingConfig(thinking_budget=0)))
            async for ch in stream:
                if ch.usage_metadata:
                    usage = (ch.usage_metadata.prompt_token_count or 0, ch.usage_metadata.candidates_token_count or 0)
                if ch.text:
                    started = True
                    yield ch.text, None
            break
        except genai_errors.ServerError:
            if started or attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)
    yield "", usage


async def run(question: str, history: list[dict] | None = None) -> AsyncIterator[dict]:
    global _search
    history = history or []
    t0 = time.perf_counter()
    stats = {"llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def done(answer, **kw):
        return {"type": "done", "answer": answer, "latency_s": round(time.perf_counter() - t0, 2), **stats, **kw}

    if GREETING.match(question):
        yield {"type": "token", "text": GREETING_REPLY}
        yield done(GREETING_REPLY, abstained=False, citations=[], followups=[])
        return
    try:
        query = question
        if history:
            yield {"type": "status", "text": "Understanding your question"}
            query, p, c = await _resolve(question, history)
            stats["llm_calls"] += 1
            stats["prompt_tokens"] += p
            stats["completion_tokens"] += c
        yield {"type": "status", "text": "Searching medical sources"}
        _search = _search or await asyncio.to_thread(SearchV2)
        docs, confidence = await asyncio.to_thread(_search.search_with_confidence, query, TOP_K)
        if not docs or confidence < MIN_DENSE:
            yield {"type": "token", "text": NOT_FOUND}
            yield done(NOT_FOUND, abstained=True, citations=[], followups=[], query=query, confidence=round(confidence, 3))
            return

        yield {"type": "status", "text": "Writing the answer"}
        split, shown = Splitter(), ""
        stats["llm_calls"] += 1
        async for text, usage in _stream_llm(_prompt(question if not history else query, docs), history):
            if usage:
                stats["prompt_tokens"] += usage[0]
                stats["completion_tokens"] += usage[1]
                continue
            out = split.feed(text)
            if out:
                shown += out
                yield {"type": "token", "text": out}
        rest, followups = split.finish()
        shown += rest
        if rest:
            yield {"type": "token", "text": rest}
        answer = shown.strip()
        cites = _cited(answer, docs)
        yield {"type": "citations", "items": cites}
        yield done(answer, abstained=False, citations=cites, followups=followups, query=query, confidence=round(confidence, 3))
    except Exception as e:  # surface to the stream; the API layer decides how to show it
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":  # terminal chat: python -m app.agent.v2
    async def chat():
        history: list[dict] = []
        print(f"MediQA v2 ({PROVIDER}). Ask a health question; empty line quits.")
        while q := (await asyncio.to_thread(input, "\nyou> ")).strip():
            answer = ""
            async for ev in run(q, history):
                if ev["type"] == "status":
                    print(f"  [{ev['text']}...]", flush=True)
                elif ev["type"] == "token":
                    print(ev["text"], end="", flush=True)
                elif ev["type"] == "error":
                    print(f"\n  ERROR: {ev['message']}")
                elif ev["type"] == "done":
                    answer = ev["answer"]
                    print(f"\n\n  sources: {[(c['n'], c['source'], c['question']) for c in ev['citations']]}")
                    print(f"  follow-ups: {ev['followups']}\n  {ev['llm_calls']} LLM call(s), {ev['latency_s']}s, abstained={ev['abstained']}")
            history += [{"role": "user", "content": q}, {"role": "assistant", "content": answer}]

    asyncio.run(chat())
