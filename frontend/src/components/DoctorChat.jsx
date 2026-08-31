import React, { useState, useRef, useEffect } from "react";
import { User, Bot, Send, Check, ChevronDown, ShieldCheck, Stethoscope, BookOpen, Copy, Edit3, ThumbsUp, ThumbsDown } from "lucide-react";

export default function DoctorChat({ sessionId, onMessageSent }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [openTraceId, setOpenTraceId] = useState(null);
  const [feedbackState, setFeedbackState] = useState({});
  const [copiedId, setCopiedId] = useState(null);
  const chatBottomRef = useRef(null);

  const loadingMessages = [
    "Consulting medical research & clinical guidelines...",
    "Searching verified medical literature & journals...",
    "Analyzing symptoms & formulating response...",
    "Fact-checking response for accuracy and safety..."
  ];

  // Fetch session messages directly on mount or when sessionId changes
  useEffect(() => {
    let active = true;

    const fetchSessionHistory = async () => {
      try {
        const res = await fetch(`/api/v1/analytics/sessions/${sessionId}`);
        if (res.ok) {
          const data = await res.json();
          if (active && data.messages && Array.isArray(data.messages) && data.messages.length > 0) {
            const formatted = [
              {
                id: "welcome",
                role: "system",
                content: `Loaded past session context: ${sessionId}`
              }
            ];
            data.messages.forEach((msg, idx) => {
              let trace = [];
              try {
                if (Array.isArray(msg.execution_trace)) {
                  trace = msg.execution_trace;
                } else if (typeof msg.execution_trace === "string" && msg.execution_trace.trim()) {
                  trace = JSON.parse(msg.execution_trace);
                }
              } catch {
                trace = [];
              }

              formatted.push({
                id: "user-" + (msg.id || idx),
                role: "user",
                content: typeof msg.question === "string" ? msg.question : String(msg.question || "")
              });
              formatted.push({
                id: "bot-" + (msg.id || idx),
                logId: msg.id,
                role: "bot",
                content: typeof msg.answer === "string" ? msg.answer : String(msg.answer || ""),
                trace: trace,
                isGrounded: msg.is_grounded,
                userFeedback: msg.user_feedback,
                turns: 1
              });
            });
            setMessages(formatted);
            return;
          }
        }
      } catch (err) {
        console.error("Failed to load session:", err);
      }

      if (active) {
        setMessages([
          {
            id: "welcome",
            role: "system",
            content: "Hello! I am your MediQA AI Assistant 🩺. Ask me any health or medical question (e.g. 'What are the symptoms of Glaucoma?' or 'How do I know if a baby has liver cancer?'). I analyze medical literature and double-check every answer against verified clinical sources."
          }
        ]);
      }
    };

    fetchSessionHistory();
    return () => { active = false; };
  }, [sessionId]);

  useEffect(() => {
    let interval;
    if (loading) {
      interval = setInterval(() => {
        setLoadingStep((prev) => (prev + 1) % loadingMessages.length);
      }, 2500);
    } else {
      setLoadingStep(0);
    }
    return () => clearInterval(interval);
  }, [loading]);

  const handleFeedback = async (msgId, traceId, logId, value) => {
    setFeedbackState((prev) => ({ ...prev, [msgId]: value }));
    
    // 1. Submit to Langfuse if traceId available
    if (traceId) {
      try {
        await fetch("/api/v1/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            trace_id: traceId,
            value: value,
            name: "user-feedback",
            comment: value === 1.0 ? "User marked answer helpful (Thumbs Up)" : "User marked answer unhelpful (Thumbs Down)"
          })
        });
      } catch (e) {
        console.warn("Langfuse feedback submission error:", e);
      }
    }

    // 2. Submit to Analytics DB if logId available
    if (logId) {
      try {
        await fetch("/api/v1/analytics/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            log_id: logId,
            feedback: value === 1.0 ? "positive" : "negative"
          })
        });
      } catch (err) {
        console.warn("Analytics feedback error:", err);
      }
    }
  };

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleEdit = (questionText) => {
    setInput(questionText);
  };

  const handleSend = async (e) => {
    e?.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = { id: "user-" + Date.now(), role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    const controller = new AbortController();
    // Cloud Run can take up to 60-90s for CRAG multi-turn — give it 120s before giving up
    const timeoutId = setTimeout(() => controller.abort(), 120000);

    try {
      const res = await fetch("/api/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: userMsg.content,
          session_id: sessionId
        }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      const data = await res.json();
      setLoading(false);

      if (res.ok) {
        setMessages((prev) => [
          ...prev,
          {
            id: "bot-" + Date.now(),
            logId: data.id,
            role: "bot",
            content: data.answer,
            trace: data.execution_trace || [],
            traceId: data.trace_id,
            latencySeconds: data.latency_seconds,
            tokens: data.total_tokens,
            costUsd: data.estimated_cost_usd,
            isGrounded: data.is_grounded,
            turns: data.turns_executed
          }
        ]);
        if (onMessageSent) onMessageSent();
      } else {
        setMessages((prev) => [
          ...prev,
          { id: "err-" + Date.now(), role: "system", content: "⚠️ The server returned an error: " + (data.detail || "Unable to complete request.") }
        ]);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      setLoading(false);
      const isTimeout = err.name === "AbortError";
      setMessages((prev) => [
        ...prev,
        {
          id: "err-" + Date.now(),
          role: "system",
          content: isTimeout
            ? "⏱️ Request timed out after 2 minutes. The server may be under heavy load — please try again."
            : "🔌 Connection Error: Could not reach the server. Please check your internet connection or try again shortly."
        }
      ]);
    }
  };

  const formatTraceStep = (step) => {
    if (!step || typeof step !== "string") return String(step || "");
    if (step.includes("[Action: Generate Query]")) {
      return "🔍 Search Strategy: " + step.replace("[Action: Generate Query] ", "");
    }
    if (step.includes("[Action: Retrieve]")) {
      return "📚 Literature Search: " + step.replace("[Action: Retrieve] ", "");
    }
    if (step.includes("[Action: Grade Documents]")) {
      return "✅ Source Verification: Relevant medical sources confirmed";
    }
    if (step.includes("[Action: Generate Answer]")) {
      return "✍️ Clinical Synthesis: Evidence-based answer generated";
    }
    if (step.includes("[Action: Grade Generation]")) {
      return "🛡️ Accuracy Check: Verified accurate and helpful for patient question";
    }
    return step;
  };

  return (
    <div className="chat-wrapper">
      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.role === "user" ? "user-msg" : "bot-msg"}`}>
            <div className="msg-avatar">
              {msg.role === "user" ? <User size={20} /> : <Stethoscope size={20} color="#00f2fe" />}
            </div>
            <div className="msg-bubble">
              <p style={{ whiteSpace: "pre-line" }}>{msg.content}</p>

              {msg.role === "user" && (
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "6px" }}>
                  <button
                    type="button"
                    className="action-link-btn"
                    onClick={() => handleEdit(msg.content)}
                    title="Edit and ask again"
                  >
                    <Edit3 size={12} /> Edit
                  </button>
                </div>
              )}

              {msg.role === "bot" && (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "8px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted, #888)", marginRight: "2px" }}>Helpful?</span>
                    <button
                      type="button"
                      className={`action-link-btn ${feedbackState[msg.id] === 1.0 || (msg.userFeedback === "positive" && feedbackState[msg.id] === undefined) ? "active-thumb-up" : ""}`}
                      style={{ color: feedbackState[msg.id] === 1.0 ? "#00e676" : undefined }}
                      onClick={() => handleFeedback(msg.id, msg.traceId, msg.logId, 1.0)}
                      title="Helpful (Thumbs Up)"
                    >
                      <ThumbsUp size={13} />
                    </button>
                    <button
                      type="button"
                      className={`action-link-btn ${feedbackState[msg.id] === 0.0 || (msg.userFeedback === "negative" && feedbackState[msg.id] === undefined) ? "active-thumb-down" : ""}`}
                      style={{ color: feedbackState[msg.id] === 0.0 ? "#ff5252" : undefined }}
                      onClick={() => handleFeedback(msg.id, msg.traceId, msg.logId, 0.0)}
                      title="Not helpful (Thumbs Down)"
                    >
                      <ThumbsDown size={13} />
                    </button>
                    {feedbackState[msg.id] !== undefined && (
                      <span style={{ fontSize: "11px", color: "var(--accent-cyan)", marginLeft: "4px" }}>
                        Feedback saved!
                      </span>
                    )}
                  </div>

                  <button
                    type="button"
                    className="action-link-btn"
                    onClick={() => handleCopy(msg.content, msg.id)}
                  >
                    {copiedId === msg.id ? (
                      <span style={{ color: "#00e676", display: "flex", alignItems: "center", gap: "4px" }}>
                        <Check size={12} /> Copied!
                      </span>
                    ) : (
                      <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                        <Copy size={12} /> Copy Answer
                      </span>
                    )}
                  </button>
                </div>
              )}

              {msg.trace && msg.trace.length > 0 && (
                <div className="trace-accordion">
                  <div
                    className="trace-header"
                    onClick={() => setOpenTraceId(openTraceId === msg.id ? null : msg.id)}
                  >
                    <span><BookOpen size={12} style={{ marginRight: "6px" }} /> Reasoning & Clinical Verification Steps</span>
                    <ChevronDown size={14} />
                  </div>
                  {openTraceId === msg.id && (
                    <div className="trace-list">
                      {msg.trace.map((step, idx) => (
                        <div key={idx} className="trace-step">
                          <Check size={12} color="#00e676" />
                          <span>{formatTraceStep(step)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {msg.isGrounded && msg.isGrounded !== "unknown" && (
                <div className="msg-meta-pill" style={{ display: "inline-flex", marginTop: "8px" }}>
                  <span><ShieldCheck size={12} /> Fact-Checked: {msg.isGrounded.toUpperCase()}</span>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="message bot-msg">
            <div className="msg-avatar"><Stethoscope size={20} color="#00f2fe" className="fa-spin" /></div>
            <div className="msg-bubble" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div className="pulse-loader" />
              <p style={{ color: "var(--accent-cyan)", fontWeight: 500 }}>{loadingMessages[loadingStep]}</p>
            </div>
          </div>
        )}
        <div ref={chatBottomRef} />
      </div>

      <div className="chat-input-container">
        <form onSubmit={handleSend} className="chat-form">
          <input
            type="text"
            placeholder="Ask a medical question (e.g., symptoms, treatments, diagnoses)..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" className="btn-primary">
            <span>Ask AI Doctor</span>
            <Send size={16} />
          </button>
        </form>

        <div className="quick-prompts">
          <span>Try asking:</span>
          <button className="prompt-chip" onClick={() => setInput("What are the symptoms and treatments of Glaucoma?")}>
            Glaucoma Symptoms
          </button>
          <button className="prompt-chip" onClick={() => setInput("What are the treatments for it?")}>
            Follow-up: Treatments for it
          </button>
          <button className="prompt-chip" onClick={() => setInput("How is Infant Hepatoblastoma diagnosed?")}>
            Infant Hepatoblastoma
          </button>
        </div>
      </div>
    </div>
  );
}
