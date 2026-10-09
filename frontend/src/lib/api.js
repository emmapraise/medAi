const BASE = "/api/v1";

async function request(path, options = {}) {
  const res = await fetch(BASE + path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : detail?.detail;
    throw new Error(message || "Something went wrong. Please try again.");
  }
  return body;
}

const json = (method, payload, signal) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
  signal,
});

export const listSessions = (ids) =>
  ids.length ? request(`/analytics/sessions?ids=${encodeURIComponent(ids.join(","))}`) : Promise.resolve([]);

export const getSession = (id) => request(`/analytics/sessions/${encodeURIComponent(id)}`);

export const deleteSession = (id) => request(`/analytics/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });

export const ask = (question, sessionId, signal) =>
  request("/ask", json("POST", { question, session_id: sessionId }, signal));

export function sendFeedback({ logId, traceId, positive }) {
  const calls = [];
  if (logId) {
    calls.push(request("/analytics/feedback", json("POST", { log_id: logId, feedback: positive ? "positive" : "negative" })));
  }
  if (traceId) {
    calls.push(request("/feedback", json("POST", { trace_id: traceId, value: positive ? 1 : 0, name: "user-feedback" })));
  }
  return Promise.allSettled(calls);
}
