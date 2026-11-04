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

// MedQuAD questions read "What is (are) Glaucoma ?"; show them the way a person would write them.
export const tidyQuestion = (q) => String(q).replace(/\s*\(are\)/i, "").replace(/\s+\?$/, "?");
