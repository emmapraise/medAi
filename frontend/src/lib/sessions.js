// Conversations are private capabilities: the browser remembers the IDs it
// created and only ever asks the server about those.
const IDS_KEY = "mediqa.sessionIds";
const MAX_REMEMBERED = 50;

const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

export function newSessionId() {
  return crypto.randomUUID();
}

export function loadSessionIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(IDS_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((id) => SESSION_ID_PATTERN.test(id)) : [];
  } catch {
    return [];
  }
}

function saveSessionIds(ids) {
  try {
    localStorage.setItem(IDS_KEY, JSON.stringify(ids.slice(0, MAX_REMEMBERED)));
  } catch {
    // Storage can be unavailable (private mode); history just won't persist.
  }
}

export function rememberSessionId(id) {
  const ids = loadSessionIds();
  if (!ids.includes(id)) saveSessionIds([id, ...ids]);
}

export function forgetSessionId(id) {
  saveSessionIds(loadSessionIds().filter((existing) => existing !== id));
}
