import { useCallback, useEffect, useState } from "react";
import { Download, Plus } from "lucide-react";
import Conversation from "./components/Conversation";
import SessionList from "./components/SessionList";
import Topics from "./components/Topics";
import { Sidebar, TabBar } from "./components/Nav";
import { deleteSession, listSessions } from "./lib/api";
import { forgetSessionId, loadSessionIds, newSessionId, rememberSessionId } from "./lib/sessions";

const WIDE = "(min-width: 900px)";
const TITLES = { ask: "MediQA", topics: "Topics", history: "History" };

function useMedia(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export default function App() {
  const wide = useMedia(WIDE);
  const [tab, setTab] = useState("ask");
  const [sessionId, setSessionId] = useState(newSessionId);
  const [sessions, setSessions] = useState([]);
  const [queued, setQueued] = useState(null); // a question to send as soon as the Ask tab is showing
  const [installPrompt, setInstallPrompt] = useState(null);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await listSessions(loadSessionIds()));
    } catch (err) {
      console.error("Could not load conversations:", err);
    }
  }, []);

  useEffect(() => {
    refreshSessions();
    const onInstallReady = (e) => {
      e.preventDefault();
      setInstallPrompt(e);
    };
    window.addEventListener("beforeinstallprompt", onInstallReady);
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch((err) => console.error("Service worker failed:", err));
    }
    return () => window.removeEventListener("beforeinstallprompt", onInstallReady);
  }, [refreshSessions]);

  const startNew = () => {
    setSessionId(newSessionId());
    setTab("ask");
  };

  const openSession = (id) => {
    setSessionId(id);
    setTab("ask");
  };

  const askFresh = (text) => {
    // A topic question is a new subject, so it gets a new conversation rather than inheriting the last one's context.
    setSessionId(newSessionId());
    setQueued({ text, n: Date.now() });
    setTab("ask");
  };

  const removeSession = async (id) => {
    try {
      await deleteSession(id);
    } catch (err) {
      console.error("Could not delete conversation:", err);
      return;
    }
    forgetSessionId(id);
    setSessions((prev) => prev.filter((s) => s.session_id !== id));
    if (id === sessionId) startNew();
  };

  const install = async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    const { outcome } = await installPrompt.userChoice;
    if (outcome === "accepted") setInstallPrompt(null);
  };

  return (
    <div className={wide ? "app is-wide" : "app"}>
      {wide && (
        <Sidebar
          tab={tab} onTab={setTab} sessions={sessions} activeId={sessionId}
          onNew={startNew} onSelect={openSession} onDelete={removeSession} onInstall={installPrompt ? install : null}
        />
      )}

      <div className="stage">
        {!wide && (
          <header className="topbar">
            <h1>{TITLES[tab]}</h1>
            {tab === "ask" && (
              <button type="button" className="tool" onClick={startNew}>
                <Plus size={18} aria-hidden="true" /> New
              </button>
            )}
          </header>
        )}

        {/* Ask stays mounted so an answer that is still streaming is not lost when switching tabs. */}
        <main className="view" hidden={tab !== "ask"}>
          <Conversation
            key={sessionId}
            sessionId={sessionId}
            queued={queued}
            onQueuedHandled={() => setQueued(null)}
            onAsked={() => { rememberSessionId(sessionId); refreshSessions(); }}
            onBrowseTopics={() => setTab("topics")}
          />
        </main>
        {tab === "topics" && <main className="view"><Topics onAsk={askFresh} /></main>}
        {tab === "history" && !wide && (
          <main className="view">
            <div className="page">
              <div className="column">
                <SessionList sessions={sessions} activeId={sessionId} onSelect={openSession} onDelete={removeSession} />
                {installPrompt && (
                  <button type="button" className="tool" onClick={install}>
                    <Download size={18} aria-hidden="true" /> Install app
                  </button>
                )}
              </div>
            </div>
          </main>
        )}

        {!wide && <TabBar tab={tab} onTab={setTab} />}
      </div>
    </div>
  );
}
