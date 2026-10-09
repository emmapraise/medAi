import { useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";
import Entry from "./Entry";
import { ask, getSession, sendFeedback } from "../lib/api";

const EXAMPLES = [
  "What are the symptoms and treatments of glaucoma?",
  "How is infant hepatoblastoma diagnosed?",
  "What causes iron deficiency anemia?",
];

const WORKING_STEPS = [
  "Searching the medical literature",
  "Reading the most relevant sources",
  "Writing your answer",
  "Checking it against the sources",
];

const REQUEST_TIMEOUT_MS = 120_000;

function fromHistory(m) {
  return {
    id: `log-${m.id}`,
    logId: m.id,
    question: m.question,
    answer: m.answer,
    trace: Array.isArray(m.execution_trace) ? m.execution_trace : [],
    isRelevant: m.is_relevant,
    isGrounded: m.is_grounded,
    isUseful: m.is_useful,
    feedback: m.user_feedback,
    latencySeconds: m.latency_seconds,
    tokens: m.total_tokens,
  };
}

function fromAnswer(question, data) {
  return {
    id: `ans-${data.id ?? crypto.randomUUID()}`,
    logId: data.id,
    traceId: data.trace_id,
    question,
    answer: data.answer,
    trace: data.execution_trace || [],
    isRelevant: data.is_relevant,
    isGrounded: data.is_grounded,
    isUseful: data.is_useful,
    latencySeconds: data.latency_seconds,
    tokens: data.total_tokens,
    cached: data.cached,
  };
}

export default function Conversation({ sessionId, onAsked }) {
  const [entries, setEntries] = useState([]);
  const [pending, setPending] = useState(null); // question currently being answered
  const [stepIndex, setStepIndex] = useState(0);
  const [error, setError] = useState("");
  const [input, setInput] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(true);
  const inputRef = useRef(null);
  const endRef = useRef(null);

  useEffect(() => {
    let active = true;
    getSession(sessionId)
      .then((data) => active && setEntries((data.messages || []).map(fromHistory)))
      .catch(() => {}) // A brand-new conversation has no history yet.
      .finally(() => active && setLoadingHistory(false));
    return () => { active = false; };
  }, [sessionId]);

  useEffect(() => {
    if (!pending) return undefined;
    setStepIndex(0);
    const timer = setInterval(() => setStepIndex((i) => Math.min(i + 1, WORKING_STEPS.length - 1)), 3500);
    return () => clearInterval(timer);
  }, [pending]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "end" });
  }, [entries.length, pending]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [input]);

  const submit = async (e) => {
    e?.preventDefault();
    const question = input.trim();
    if (!question || pending) return;

    setInput("");
    setError("");
    setPending(question);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const data = await ask(question, sessionId, controller.signal);
      setEntries((prev) => [...prev, fromAnswer(question, data)]);
      onAsked();
    } catch (err) {
      setInput(question); // Give the question back so nothing has to be retyped.
      setError(
        err.name === "AbortError"
          ? "This is taking longer than expected. Your question is still in the box; try sending it again."
          : err instanceof TypeError
            ? "Can't reach the server. Check your connection, then send your question again."
            : err.message
      );
    } finally {
      clearTimeout(timeout);
      setPending(null);
    }
  };

  const rate = (entry, positive) => {
    setEntries((prev) => prev.map((x) => (x.id === entry.id ? { ...x, feedback: positive ? "positive" : "negative" } : x)));
    sendFeedback({ logId: entry.logId, traceId: entry.traceId, positive });
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) submit(e);
  };

  const edit = (question) => {
    setInput(question);
    inputRef.current?.focus();
  };

  const isEmpty = !loadingHistory && entries.length === 0 && !pending;

  return (
    <div className="conversation">
      <div className="feed">
        <div className="feed-inner">
          {isEmpty && (
            <section className="welcome">
              <h1>What would you like to understand about your health?</h1>
              <p>
                Ask in your own words. MediQA finds relevant medical sources, writes an answer from them, and shows
                you how it checked that answer.
              </p>
              <ul className="examples" aria-label="Example questions">
                {EXAMPLES.map((q) => (
                  <li key={q}>
                    <button type="button" className="example" onClick={() => edit(q)}>{q}</button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div role="log" aria-live="polite" aria-relevant="additions">
            {entries.map((entry) => (
              <Entry key={entry.id} entry={entry} onEdit={edit} onFeedback={rate} />
            ))}
          </div>

          {pending && (
            <article className="entry is-pending" aria-busy="true">
              <h2 className="entry-question">{pending}</h2>
              <p className="working" role="status">
                <span className="working-dot" aria-hidden="true" />
                {WORKING_STEPS[stepIndex]}…
              </p>
            </article>
          )}

          {error && <p className="notice" role="alert">{error}</p>}
          <div ref={endRef} />
        </div>
      </div>

      <div className="composer-wrap">
        <form className="composer" onSubmit={submit}>
          <label htmlFor="question" className="sr-only">Your health question</label>
          <textarea
            id="question"
            ref={inputRef}
            rows={1}
            value={input}
            maxLength={2000}
            placeholder="Ask about a symptom, condition, or treatment"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <button type="submit" className="btn btn-solid send" disabled={!input.trim() || !!pending}>
            <ArrowUp size={16} aria-hidden="true" /> Ask
          </button>
        </form>
        <p className="disclaimer">
          General information, not a diagnosis or medical advice. In an emergency, call your local emergency number.
        </p>
      </div>
    </div>
  );
}
