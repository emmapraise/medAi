import { useState } from "react";
import { Download, Plus, Trash2, X } from "lucide-react";
import { timeAgo } from "../lib/format";

export default function Sidebar({ open, sessions, activeId, onNew, onSelect, onDelete, onClose, onInstall }) {
  const [confirmingId, setConfirmingId] = useState(null);

  return (
    <>
      {open && <div className="scrim" onClick={onClose} aria-hidden="true" />}
      <aside className={`rail ${open ? "is-open" : ""}`} aria-label="Conversations">
        <div className="rail-head">
          <div className="brand">
            <span className="brand-name">MediQA</span>
            <span className="brand-sub">Answers checked against medical sources</span>
          </div>
          <button type="button" className="icon-btn rail-close" onClick={onClose} aria-label="Close conversations">
            <X size={20} />
          </button>
        </div>

        <button type="button" className="btn btn-solid" onClick={onNew}>
          <Plus size={16} aria-hidden="true" /> New question
        </button>

        <h2 className="rail-heading">Your conversations</h2>
        {sessions.length === 0 ? (
          <p className="rail-empty">Questions you ask are saved here, on this device.</p>
        ) : (
          <ul className="session-list">
            {sessions.map((s) => {
              const confirming = confirmingId === s.session_id;
              return (
                <li key={s.session_id} className={s.session_id === activeId ? "session is-active" : "session"}>
                  <button
                    type="button"
                    className="session-open"
                    onClick={() => onSelect(s.session_id)}
                    aria-current={s.session_id === activeId ? "true" : undefined}
                  >
                    <span className="session-title">{s.preview}</span>
                    <span className="session-meta">
                      {s.total_queries} {s.total_queries === 1 ? "question" : "questions"} · {timeAgo(s.last_active_at)}
                    </span>
                  </button>
                  {confirming ? (
                    <span className="session-confirm">
                      <button type="button" className="link-btn danger" onClick={() => { setConfirmingId(null); onDelete(s.session_id); }}>
                        Delete
                      </button>
                      <button type="button" className="link-btn" onClick={() => setConfirmingId(null)}>
                        Keep
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="icon-btn session-delete"
                      onClick={() => setConfirmingId(s.session_id)}
                      aria-label={`Delete conversation: ${s.preview}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {onInstall && (
          <button type="button" className="btn btn-quiet rail-install" onClick={onInstall}>
            <Download size={16} aria-hidden="true" /> Install app
          </button>
        )}
      </aside>
    </>
  );
}
