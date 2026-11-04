import { useEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import Answer from "./Answer";
import SourceSheet from "./SourceSheet";
import { askStream, getSession, sendFeedback } from "../lib/api";

const NOTICE = "AI-written from NIH sources. It can make mistakes and isn't medical advice. In an emergency, call your local emergency number.";

const STARTERS = [
  "What are the symptoms of glaucoma?",
  "How is infant hepatoblastoma diagnosed?",
  "What causes iron deficiency anemia?",
];

function fromHistory(m) {
  const extra = m.extra || {};
  return {
    id: `log-${m.id}`,
    logId: m.id,
    question: m.question,
    answer: m.answer,
    citations: extra.citations || [],
    followups: extra.followups || [],
    safety: extra.safety || null,
    abstained: !!extra.abstained,
    feedback: m.user_feedback,
    state: "done",
  };
}

export default function Conversation({ sessionId, queued, onQueuedHandled, onAsked, onBrowseTopics }) {
  const [entries, setEntries] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [sheet, setSheet] = useState(null); // { entryId, n }
  const controller = useRef(null);
  const feed = useRef(null);
  const field = useRef(null);
  const stick = useRef(true); // follow the stream only while the reader is at the bottom

  useEffect(() => {
    let active = true;
    getSession(sessionId)
      .then((data) => active && setEntries((prev) => (prev.length ? prev : (data.messages || []).map(fromHistory))))
      .catch(() => {}) // A brand-new conversation has no history yet.
      .finally(() => active && setLoadingHistory(false));
    return () => {
      active = false;
      controller.current?.abort();
    };
  }, [sessionId]);

  useEffect(() => {
    if (stick.current && feed.current) feed.current.scrollTop = feed.current.scrollHeight;
  }, [entries]);

  useEffect(() => {
    const el = field.current;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const update = (id, patch) =>
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...(typeof patch === "function" ? patch(e) : patch) } : e)));

  const send = async (raw) => {
    const question = raw.trim();
    if (!question || controller.current) return;
    const id = crypto.randomUUID();
    const ctl = new AbortController();
    controller.current = ctl;
    stick.current = true;
    setBusy(true);
    setInput("");
    setEntries((prev) => [...prev, { id, question, answer: "", citations: [], followups: [], state: "streaming", status: "Starting" }]);

    let finished = false;
    try {
      for await (const ev of askStream(question, sessionId, ctl.signal)) {
        if (ev.type === "status") update(id, { status: ev.text });
        else if (ev.type === "token") update(id, (e) => ({ answer: e.answer + ev.text }));
        else if (ev.type === "citations") update(id, { citations: ev.items });
        else if (ev.type === "done") {
          finished = true;
          update(id, { state: "done", logId: ev.id, answer: ev.answer, citations: ev.citations, followups: ev.followups, safety: ev.safety, abstained: ev.abstained });
          onAsked();
        } else if (ev.type === "error") {
          finished = true;
          update(id, { state: "error", error: "I couldn't write an answer just now." });
        }
      }
      if (!finished) update(id, { state: "error", error: "The connection dropped before the answer finished." });
    } catch (err) {
      if (err.name === "AbortError") update(id, { state: "stopped" });
      else update(id, { state: "error", error: err instanceof TypeError ? "Can't reach the server. Check your connection." : err.message });
    } finally {
      controller.current = null;
      setBusy(false);
    }
  };

  useEffect(() => {
    if (queued) {
      send(queued.text);
      onQueuedHandled();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per queued request, not on every render
  }, [queued?.n]);

  const rate = (entry, positive) => {
    update(entry.id, { feedback: positive ? "positive" : "negative" });
    sendFeedback({ logId: entry.logId, positive }).catch(() => update(entry.id, { feedback: null }));
  };

  const retry = (entry) => {
    setEntries((prev) => prev.filter((e) => e.id !== entry.id));
    send(entry.question);
  };

  const edit = (question) => {
    setInput(question);
    field.current.focus();
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(input);
    }
  };

  const last = entries[entries.length - 1];
  const sheetEntry = sheet && entries.find((e) => e.id === sheet.entryId);

  return (
    <div className="conversation">
      <div className="feed" ref={feed} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120; }}>
        <div className="column">
          {!loadingHistory && entries.length === 0 && (
            <section className="welcome">
              <h1>Ask about a health topic</h1>
              <p>
                Answers are written by AI from NIH medical sources. Every answer shows the sources it used, so you can
                check them yourself.
              </p>
              <h2>Try asking</h2>
              <ul className="followups">
                {STARTERS.map((q) => (
                  <li key={q}><button type="button" className="suggest" onClick={() => send(q)}>{q}</button></li>
                ))}
              </ul>
              <button type="button" className="tool" onClick={onBrowseTopics}>Browse topics instead</button>
            </section>
          )}

          {entries.map((entry) => (
            <Answer
              key={entry.id}
              entry={entry}
              isLast={entry === last}
              onCite={(e, n) => setSheet({ entryId: e.id, n })}
              onAsk={send}
              onEdit={edit}
              onRetry={retry}
              onFeedback={rate}
            />
          ))}
          {/* Same notice as under the composer; shown here instead when text is large or the screen is short. */}
          <p className="fine feed-fine">{NOTICE}</p>
        </div>
      </div>

      <div className="composer-wrap">
        <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
          <label htmlFor="question" className="sr-only">Your health question</label>
          <textarea
            id="question"
            ref={field}
            rows={1}
            value={input}
            maxLength={2000}
            placeholder="Ask a health question"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
          />
          {busy ? (
            <button type="button" className="send" onClick={() => controller.current?.abort()} aria-label="Stop answering">
              <Square size={16} fill="currentColor" aria-hidden="true" />
            </button>
          ) : (
            <button type="submit" className="send" disabled={!input.trim()} aria-label="Send question">
              <ArrowUp size={20} aria-hidden="true" />
            </button>
          )}
        </form>
        <p className="fine composer-fine">{NOTICE}</p>
      </div>

      {sheetEntry && <SourceSheet cites={sheetEntry.citations} active={sheet.n} onClose={() => setSheet(null)} />}
    </div>
  );
}
