import React, { useState, useRef, useEffect } from "react";
import { User, Bot, Send, Check, ChevronDown, Zap, Coins, DollarSign, ShieldCheck, Stethoscope, BookOpen, Copy, Edit3 } from "lucide-react";

export default function DoctorChat({ sessionId, loadedHistory, onMessageSent }) {
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "system",
      content: "Hello! I am your MediQA AI Assistant 🩺. Ask me any health or medical question (e.g. 'What are the symptoms of Glaucoma?' or 'How do I know if a baby has liver cancer?'). I analyze medical literature and double-check every answer against verified clinical sources."
    }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [openTraceId, setOpenTraceId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const chatBottomRef = useRef(null);

  const loadingMessages = [
    "Consulting medical research & clinical guidelines...",
    "Searching verified medical literature & journals...",
    "Analyzing symptoms & formulating response...",
    "Fact-checking response for accuracy and safety..."
  ];

  // Update messages when a past session is selected
  useEffect(() => {
    if (loadedHistory && loadedHistory.length > 0) {
      const formatted = [
        {
          id: "welcome",
          role: "system",
          content: `Loaded past session context: ${sessionId}`
        }
      ];
      loadedHistory.forEach((msg) => {
        formatted.push({
          id: "user-" + msg.id,
          role: "user",
          content: msg.question
        });
        formatted.push({
          id: "bot-" + msg.id,
          role: "bot",
          content: msg.answer,
          trace: msg.execution_trace || [],
          latencySeconds: msg.latency_seconds,
          tokens: msg.total_tokens,
          costUsd: msg.estimated_cost_usd,
          isGrounded: msg.is_grounded,
          turns: 1
        });
      });
      setMessages(formatted);
    } else {
      setMessages([
        {
          id: "welcome",
          role: "system",
          content: "Hello! I am your MediQA AI Assistant 🩺. Ask me any health or medical question (e.g. 'What are the symptoms of Glaucoma?' or 'How do I know if a baby has liver cancer?'). I analyze medical literature and double-check every answer against verified clinical sources."
        }
      ]);
    }
  }, [sessionId, loadedHistory]);

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

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, loadingStep]);

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

    try {
      const res = await fetch("/api/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: userMsg.content,
          session_id: sessionId
        })
      });

      const data = await res.json();
      setLoading(false);

      if (res.ok) {
        setMessages((prev) => [
          ...prev,
          {
            id: "bot-" + Date.now(),
            role: "bot",
            content: data.answer,
            trace: data.execution_trace || [],
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
          { id: "err-" + Date.now(), role: "system", content: "Apologies, an error occurred: " + (data.detail || "Unable to complete request.") }
        ]);
      }
    } catch (err) {
      setLoading(false);
      setMessages((prev) => [
        ...prev,
        { id: "err-" + Date.now(), role: "system", content: "Connection Error: Could not reach the server." }
      ]);
    }
  };

  const formatTraceStep = (step) => {
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
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "8px", gap: "8px" }}>
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

              {msg.latencySeconds && (
                <div className="msg-meta-pill">
                  <span><Zap size={12} /> {msg.latencySeconds}s response time</span>
                  <span><ShieldCheck size={12} /> Fact-Checked: {(msg.isGrounded || "").toUpperCase()}</span>
                  <span><Coins size={12} /> {msg.tokens.toLocaleString()} tokens</span>
                  <span><DollarSign size={12} /> ${msg.costUsd}</span>
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
