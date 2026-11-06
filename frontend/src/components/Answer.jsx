import { useState } from "react";
import { Check, Copy, Info, LifeBuoy, Pencil, RotateCcw, SearchX, Siren, Stethoscope, ThumbsDown, ThumbsUp } from "lucide-react";
import RichText from "./RichText";

// Safety and "not found" replies are not answers, so they are not styled like answers.
const NOTICES = {
  emergency: { icon: Siren, title: "This may be an emergency", tone: "alert" },
  self_harm: { icon: LifeBuoy, title: "You're not alone", tone: "alert" },
  personal_advice: { icon: Stethoscope, title: "Best answered by a clinician", tone: "info" },
  injection: { icon: Info, title: "I can only help with health questions", tone: "info" },
  notfound: { icon: SearchX, title: "Not found in NIH sources", tone: "info" },
};

function Notice({ kind, children }) {
  const { icon: Icon, title, tone } = NOTICES[kind];
  return (
    <section className={`notice notice-${tone}`} role={tone === "alert" ? "alert" : undefined}>
      <Icon size={22} aria-hidden="true" />
      <div>
        <h3>{title}</h3>
        {children}
      </div>
    </section>
  );
}

export default function Answer({ entry, isLast, onCite, onAsk, onEdit, onRetry, onFeedback, readOnly = false }) {
  const [copied, setCopied] = useState(false);
  const { state, answer, citations, followups, feedback } = entry;
  const kind = entry.safety || (entry.abstained ? "notfound" : null);
  const finished = state === "done";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* Clipboard can be blocked; there is nothing useful to show. */
    }
  };

  return (
    <article className="turn">
      <div className="you-row">
        <h2 className="you">
          <span className="sr-only">You asked: </span>
          {entry.question}
        </h2>
        {!entry.safety && !readOnly && (
          <button type="button" className="tool icon-only" onClick={() => onEdit(entry.question)} aria-label="Edit this question">
            <Pencil size={18} aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="reply">
        <h3 className="sr-only">MediQA's answer</h3>

        {state === "streaming" && !answer && (
          <p className="status" role="status">
            <span className="pulse" aria-hidden="true" />
            {entry.status}…
          </p>
        )}

        {kind && finished ? (
          <Notice kind={kind}><p>{answer}</p></Notice>
        ) : (
          answer && (
            <div className="answer" aria-busy={state === "streaming"}>
              <RichText text={answer} cites={citations} onCite={(n) => onCite(entry, n)} />
            </div>
          )
        )}

        {state === "stopped" && (
          <p className="inline-note">
            Stopped. <button type="button" className="tool" onClick={() => onRetry(entry)}><RotateCcw size={16} aria-hidden="true" /> Ask again</button>
          </p>
        )}
        {state === "error" && (
          <p className="inline-note is-error" role="alert">
            {entry.error}{" "}
            <button type="button" className="tool" onClick={() => onRetry(entry)}><RotateCcw size={16} aria-hidden="true" /> Try again</button>
          </p>
        )}

        {finished && !kind && citations.length > 0 && (
          <nav className="sources" aria-label="Sources for this answer">
            <span className="label">Sources</span>
            <ul>
              {citations.map((c) => (
                <li key={c.n}>
                  <button type="button" className="chip" onClick={() => onCite(entry, c.n)}>
                    <span className="chip-n" aria-hidden="true">{c.n}</span>
                    <span className="sr-only">Source {c.n}: </span>
                    {c.source}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        )}

        {!readOnly && finished && !entry.safety && !!entry.logId && (
          <div className="actions" role="group" aria-label="Answer actions">
            <button type="button" className={`tool icon-only ${feedback === "positive" ? "is-on" : ""}`} aria-pressed={feedback === "positive"}
              aria-label="Helpful" onClick={() => onFeedback(entry, true)}>
              <ThumbsUp size={18} aria-hidden="true" />
            </button>
            <button type="button" className={`tool icon-only ${feedback === "negative" ? "is-on" : ""}`} aria-pressed={feedback === "negative"}
              aria-label="Not helpful" onClick={() => onFeedback(entry, false)}>
              <ThumbsDown size={18} aria-hidden="true" />
            </button>
            {!kind && (
              <button type="button" className="tool" onClick={copy}>
                {copied ? <Check size={18} aria-hidden="true" /> : <Copy size={18} aria-hidden="true" />}
                <span role="status">{copied ? "Copied" : "Copy"}</span>
              </button>
            )}
          </div>
        )}

        {!readOnly && finished && isLast && followups?.length > 0 && !entry.safety && (
          <section aria-label="Suggested follow-up questions">
            <ul className="followups">
              {followups.map((q) => (
                <li key={q}><button type="button" className="suggest" onClick={() => onAsk(q)}>{q}</button></li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </article>
  );
}
