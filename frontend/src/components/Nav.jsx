import { Clock, Compass, Download, MessageCircle, Plus } from "lucide-react";
import SessionList from "./SessionList";

const TABS = [
  { id: "ask", label: "Ask", icon: MessageCircle },
  { id: "topics", label: "Topics", icon: Compass },
  { id: "history", label: "History", icon: Clock },
];

/** Narrow screens: a tab bar. Same three destinations as the sidebar, so nothing changes with size. */
export function TabBar({ tab, onTab }) {
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button key={id} type="button" className={tab === id ? "tab is-active" : "tab"} aria-current={tab === id ? "page" : undefined} onClick={() => onTab(id)}>
          <Icon size={22} aria-hidden="true" />
          {label}
        </button>
      ))}
    </nav>
  );
}

/** Wide screens: a sidebar with the destinations on top and the conversation list below. */
export function Sidebar({ tab, onTab, sessions, activeId, onNew, onSelect, onDelete, onInstall }) {
  return (
    <aside className="sidebar">
      <p className="brand">MediQA</p>
      <button type="button" className="primary" onClick={onNew}>
        <Plus size={18} aria-hidden="true" /> New question
      </button>
      <nav aria-label="Main">
        <ul className="side-nav">
          {TABS.filter((t) => t.id !== "history").map(({ id, label, icon: Icon }) => (
            <li key={id}>
              <button type="button" className={tab === id ? "side-item is-active" : "side-item"} aria-current={tab === id ? "page" : undefined} onClick={() => onTab(id)}>
                <Icon size={20} aria-hidden="true" /> {label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <h2 className="section-label">Conversations</h2>
      <div className="side-scroll">
        <SessionList sessions={sessions} activeId={activeId} onSelect={onSelect} onDelete={onDelete} />
      </div>
      {onInstall && (
        <button type="button" className="tool" onClick={onInstall}>
          <Download size={18} aria-hidden="true" /> Install app
        </button>
      )}
    </aside>
  );
}
