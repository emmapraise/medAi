import React, { useState, useEffect } from "react";
import { Stethoscope, UserCheck, BookOpen, BarChart3, Plus, MessageSquare, History, Download, Trash2 } from "lucide-react";
import DoctorChat from "./components/DoctorChat";
import HybridSearch from "./components/HybridSearch";
import AnalyticsDashboard from "./components/AnalyticsDashboard";

export default function App() {
  const [activeTab, setActiveTab] = useState("chat");
  const [sessionId, setSessionId] = useState(() => "patient_session_" + Math.floor(1000 + Math.random() * 9000));
  const [pastSessions, setPastSessions] = useState([]);
  const [loadedHistory, setLoadedHistory] = useState([]);
  const [deferredPrompt, setDeferredPrompt] = useState(null);

  const fetchPastSessions = async () => {
    try {
      const res = await fetch("/api/v1/analytics/sessions");
      if (res.ok) {
        const data = await res.json();
        setPastSessions(data || []);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchPastSessions();

    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    });

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").then((reg) => {
        console.log("[PWA] Service Worker registered:", reg.scope);
      });
    }
  }, []);

  const handleNewSession = () => {
    const newId = "patient_session_" + Math.floor(1000 + Math.random() * 9000);
    setSessionId(newId);
    setLoadedHistory([]);
    setActiveTab("chat");
  };

  const handleSelectSession = async (sId) => {
    setSessionId(sId);
    setActiveTab("chat");
    try {
      const res = await fetch(`/api/v1/analytics/sessions/${sId}`);
      if (res.ok) {
        const data = await res.json();
        setLoadedHistory(data.messages || []);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteSession = async (e, sId) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete session ${sId}?`)) return;

    try {
      const res = await fetch(`/api/v1/analytics/sessions/${sId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        setPastSessions((prev) => prev.filter((s) => s.session_id !== sId));
        if (sessionId === sId) {
          handleNewSession();
        }
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  const handleInstallPWA = () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then((choice) => {
        if (choice.outcome === "accepted") {
          setDeferredPrompt(null);
        }
      });
    } else {
      alert("PWA Install Ready! Use your browser's 'Add to Home Screen' option.");
    }
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><Stethoscope size={24} /></div>
          <div className="brand-text">
            <h2>MediQA<span>.AI</span></h2>
            <p>Medical Intelligence & RAG</p>
          </div>
        </div>

        <button className="btn-primary" onClick={handleNewSession} style={{ justifyContent: "center", width: "100%" }}>
          <Plus size={18} /> <span>New Chat</span>
        </button>

        <nav className="nav-menu">
          <button className={`nav-item ${activeTab === "chat" ? "active" : ""}`} onClick={() => setActiveTab("chat")}>
            <UserCheck size={18} /> <span>AI Doctor Chat</span>
          </button>
          <button className={`nav-item ${activeTab === "search" ? "active" : ""}`} onClick={() => setActiveTab("search")}>
            <BookOpen size={18} /> <span>Literature Search</span>
          </button>
          <button className={`nav-item ${activeTab === "analytics" ? "active" : ""}`} onClick={() => setActiveTab("analytics")}>
            <BarChart3 size={18} /> <span>Performance & Costs</span>
          </button>
        </nav>

        {/* Past Sessions List */}
        <div className="past-sessions-container">
          <div className="sessions-header">
            <History size={14} /> <span>Past Conversations</span>
          </div>
          <div className="sessions-list">
            {pastSessions.map((s) => (
              <div
                key={s.session_id}
                className={`session-item ${s.session_id === sessionId ? "active" : ""}`}
                onClick={() => handleSelectSession(s.session_id)}
              >
                <MessageSquare size={14} className="session-icon" />
                <div className="session-info">
                  <span className="session-title">{s.preview ? s.preview.substring(0, 22) + "..." : s.session_id}</span>
                  <span className="session-sub">{s.total_queries} turns • {s.session_id}</span>
                </div>
                <button
                  type="button"
                  className="delete-session-btn"
                  onClick={(e) => handleDeleteSession(e, s.session_id)}
                  title="Delete Session"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {deferredPrompt && (
          <button className="pwa-install-btn" onClick={handleInstallPWA}>
            <Download size={16} /> <span>Install PWA App</span>
          </button>
        )}
      </aside>

      <main className="main-content">
        <header className="top-header">
          <div className="header-title">
            <h1>MediQA Assistant</h1>
            <p>Evidence-based AI medical answering verified against clinical literature</p>
          </div>
          <div className="header-actions">
            <div className="session-badge">
              <span>Active Session: {sessionId}</span>
              <button onClick={handleNewSession} title="Start New Session"><Plus size={16} /></button>
            </div>
          </div>
        </header>

        <div className="tab-content">
          {activeTab === "chat" && (
            <DoctorChat
              sessionId={sessionId}
              loadedHistory={loadedHistory}
              onMessageSent={fetchPastSessions}
            />
          )}
          {activeTab === "search" && <HybridSearch />}
          {activeTab === "analytics" && <AnalyticsDashboard />}
        </div>
      </main>
    </div>
  );
}
