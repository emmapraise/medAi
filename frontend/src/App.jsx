import { useCallback, useEffect, useState } from "react";
import { Menu } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Conversation from "./components/Conversation";
import { deleteSession, listSessions } from "./lib/api";
import { forgetSessionId, loadSessionIds, newSessionId, rememberSessionId } from "./lib/sessions";

export default function App() {
  const [sessionId, setSessionId] = useState(newSessionId);
  const [sessions, setSessions] = useState([]);
  const [installPrompt, setInstallPrompt] = useState(null);
  const [navOpen, setNavOpen] = useState(false);

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
    setNavOpen(false);
  };

  const openSession = (id) => {
    setSessionId(id);
    setNavOpen(false);
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

  const handleAsked = () => {
    rememberSessionId(sessionId);
    refreshSessions();
  };

  const install = async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    const { outcome } = await installPrompt.userChoice;
    if (outcome === "accepted") setInstallPrompt(null);
  };

  return (
    <div className="app">
      <Sidebar
        open={navOpen}
        sessions={sessions}
        activeId={sessionId}
        onNew={startNew}
        onSelect={openSession}
        onDelete={removeSession}
        onClose={() => setNavOpen(false)}
        onInstall={installPrompt ? install : null}
      />
      <main className="main">
        <header className="topbar">
          <button type="button" className="icon-btn" onClick={() => setNavOpen(true)} aria-label="Open conversations">
            <Menu size={20} />
          </button>
          <span className="topbar-title">MediQA</span>
        </header>
        <Conversation key={sessionId} sessionId={sessionId} onAsked={handleAsked} />
      </main>
    </div>
  );
}
