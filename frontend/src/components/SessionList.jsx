import { useState } from "react";
import { Trash2 } from "lucide-react";
import { timeAgo } from "../lib/format";

export default function SessionList({ sessions, activeId, onSelect, onDelete }) {
  const [confirmingId, setConfirmingId] = useState(null);

  if (sessions.length === 0) {
    return <p className="empty">Conversations you start are saved here so you can come back to them. You can delete any of them.</p>;
  }

  return (
    <ul className="sessions">
      {sessions.map((s) => {
        const confirming = confirmingId === s.session_id;
        const active = s.session_id === activeId;
        return (
          <li key={s.session_id} className={active ? "session is-active" : "session"}>
            <button type="button" className="session-open" onClick={() => onSelect(s.session_id)} aria-current={active ? "true" : undefined}>
              <span className="session-title">{s.preview}</span>
              <span className="session-meta">
                {s.total_queries} {s.total_queries === 1 ? "question" : "questions"} · {timeAgo(s.last_active_at)}
              </span>
            </button>
            {confirming ? (
              <span className="confirm" role="group" aria-label="Delete this conversation?">
                <button type="button" className="tool danger" onClick={() => { setConfirmingId(null); onDelete(s.session_id); }}>Delete</button>
                <button type="button" className="tool" onClick={() => setConfirmingId(null)}>Cancel</button>
              </span>
            ) : (
              <button type="button" className="tool icon-only" onClick={() => setConfirmingId(s.session_id)} aria-label={`Delete conversation: ${s.preview}`}>
                <Trash2 size={18} aria-hidden="true" />
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
