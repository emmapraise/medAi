const V1 = "/api/v1";
const V2 = "/api/v2";

async function failure(res) {
  const body = await res.json().catch(() => ({}));
  const detail = body.detail;
  const message = typeof detail === "string" ? detail : detail?.detail;
  return new Error(message || "Something went wrong. Please try again.");
}

async function request(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) throw await failure(res);
  return res.json().catch(() => ({}));
}

const json = (method, payload, signal) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
  signal,
});

export const listSessions = (ids) =>
  ids.length ? request(`${V1}/analytics/sessions?ids=${encodeURIComponent(ids.join(","))}`) : Promise.resolve([]);

export const getSession = (id) => request(`${V1}/analytics/sessions/${encodeURIComponent(id)}`);

export const deleteSession = (id) => request(`${V1}/analytics/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });

export const getTopics = (q, signal) => request(`${V2}/topics?q=${encodeURIComponent(q)}`, { signal });

// Read-only share links. The token in a link is not the conversation's id (the id would also allow writing and deleting).
const shareUrl = (id) => `${V2}/sessions/${encodeURIComponent(id)}/share`;
export const getShare = (id) => request(shareUrl(id));
export const createShare = (id) => request(shareUrl(id), { method: "POST" });
export const stopShare = (id) => request(shareUrl(id), { method: "DELETE" });
export const getShared = (token) => request(`${V2}/shared/${encodeURIComponent(token)}`);

export function sendFeedback({ logId, positive }) {
  return request(`${V1}/analytics/feedback`, json("POST", { log_id: logId, feedback: positive ? "positive" : "negative" }));
}

/** Server-sent events from POST /api/v2/ask, as an async iterator of parsed event objects. */
export async function* askStream(question, sessionId, signal) {
  const res = await fetch(`${V2}/ask`, json("POST", { question, session_id: sessionId }, signal));
  if (!res.ok) throw await failure(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = block.split("\n").find((line) => line.startsWith("data: "));
      if (data) yield JSON.parse(data.slice(6));
    }
  }
}
