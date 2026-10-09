import { useState } from "react";
import { Check, ChevronRight, Copy, Minus, Pencil, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { describeStep } from "../lib/format";

const CHECKS = [
  ["isRelevant", "Sources were relevant"],
  ["isGrounded", "Answer matches the sources"],
  ["isUseful", "Answer addresses your question"],
];

const OUTCOME = {
  yes: { icon: Check, word: "Yes", tone: "ok" },
  no: { icon: X, word: "No", tone: "warn" },
};

function Ledger({ entry }) {
  const hasChecks = CHECKS.some(([key]) => entry[key] && entry[key] !== "unknown");
  if (!hasChecks && !entry.trace?.length) return null;

  return (
    <aside className="ledger" aria-label="How this answer was checked">
      <h3 className="ledger-title">How it was checked</h3>
      {hasChecks && (
        <ul className="checks">
          {CHECKS.map(([key, label]) => {
            const { icon: Icon, word, tone } = OUTCOME[entry[key]] || { icon: Minus, word: "Not recorded", tone: "mute" };
            return (
              <li key={key} className={`check check-${tone}`}>
                <Icon size={15} aria-hidden="true" />
                <span className="check-label">{label}</span>
                <span className="check-word">{word}</span>
              </li>
            );
          })}
        </ul>
      )}

      {entry.trace?.length > 0 && (
        <details className="steps">
          <summary>
            <ChevronRight size={14} aria-hidden="true" /> Steps taken
          </summary>
          <ol>
            {entry.trace.map((raw, i) => {
              const { label, detail } = describeStep(raw);
              return (
                <li key={i}>
                  <span>{label}</span>
                  {detail && <small>{detail}</small>}
                </li>
              );
            })}
          </ol>
        </details>
      )}

      {entry.latencySeconds != null && (
        <p className="ledger-meta">
          {entry.cached ? "Saved answer" : `${entry.latencySeconds.toFixed(1)}s`}
          {entry.tokens ? ` · ${entry.tokens.toLocaleString()} tokens` : ""}
        </p>
      )}
    </aside>
  );
}

export default function Entry({ entry, onEdit, onFeedback }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(entry.answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* Clipboard is blocked in some contexts; nothing useful to show. */
    }
  };

  const vote = entry.feedback;

  return (
    <article className="entry">
      <header className="entry-head">
        <h2 className="entry-question">{entry.question}</h2>
        <button type="button" className="link-btn" onClick={() => onEdit(entry.question)}>
          <Pencil size={13} aria-hidden="true" /> Edit and ask again
        </button>
      </header>

      <div className="entry-body">
        <div className="answer">
          {entry.answer.split(/\n{2,}/).map((para, i) => (
            <p key={i}>{para}</p>
          ))}
        </div>
        <Ledger entry={entry} />
      </div>

      <footer className="entry-foot">
        <span className="foot-label" id={`helpful-${entry.id}`}>Was this helpful?</span>
        <div role="group" aria-labelledby={`helpful-${entry.id}`} className="foot-group">
          <button
            type="button"
            className={`icon-btn ${vote === "positive" ? "is-on" : ""}`}
            aria-pressed={vote === "positive"}
            aria-label="Yes, helpful"
            onClick={() => onFeedback(entry, true)}
          >
            <ThumbsUp size={15} />
          </button>
          <button
            type="button"
            className={`icon-btn ${vote === "negative" ? "is-on is-warn" : ""}`}
            aria-pressed={vote === "negative"}
            aria-label="No, not helpful"
            onClick={() => onFeedback(entry, false)}
          >
            <ThumbsDown size={15} />
          </button>
        </div>
        {vote && <span className="foot-note" role="status">Thanks, your feedback was saved.</span>}
        <button type="button" className="link-btn foot-copy" onClick={copy}>
          {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
          {copied ? "Copied" : "Copy answer"}
        </button>
      </footer>
    </article>
  );
}
