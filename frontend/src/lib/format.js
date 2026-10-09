const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function timeAgo(iso) {
  if (!iso) return "";
  const seconds = (new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime() - Date.now()) / 1000;
  const steps = [["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

// Maps agent log lines to plain-language steps; the bracketed detail is kept as a second line.
const STEP_LABELS = [
  ["Conversational Greeting", "Replied directly, no search needed"],
  ["Generate Query", "Turned your question into a search"],
  ["Rewrite Query", "Tried a different search"],
  ["Retrieve", "Searched the medical literature"],
  ["Grade Documents", "Checked the sources were relevant"],
  ["Generate Answer", "Wrote the answer from those sources"],
  ["Grade Generation", "Checked the answer against the sources"],
];

export function describeStep(raw) {
  const text = String(raw || "");
  const match = text.match(/^\[Action: ([^\]]+)\]\s*(.*)$/s);
  if (!match) return { label: text, detail: "" };
  const [, action, detail] = match;
  const known = STEP_LABELS.find(([key]) => action.startsWith(key));
  return { label: known ? known[1] : action, detail };
}
