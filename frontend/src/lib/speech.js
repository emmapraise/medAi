// Dictation through the browser's own SpeechRecognition. Where it exists (Chrome, Edge, Safari) the browser asks for
// the microphone itself; where it does not (Firefox) the mic button is simply not shown.
const Recognition = () => window.SpeechRecognition || window.webkitSpeechRecognition;

export const dictationSupported = () => !!Recognition();

const BLOCKED = "Microphone access is blocked. Allow it in your browser's site settings to dictate.";
const ERRORS = {
  "not-allowed": BLOCKED,
  "service-not-allowed": BLOCKED,
  "no-speech": "I didn't hear anything. Try again.",
  network: "Dictation needs an internet connection.",
};

/** Starts listening; onText gets the whole transcript so far, onEnd gets an error message or "". Returns stop(). */
export function startDictation({ onText, onEnd }) {
  const rec = new (Recognition())();
  let error = "";
  rec.lang = navigator.language;
  rec.interimResults = true;
  rec.continuous = false;
  rec.onresult = (e) => onText([...e.results].map((r) => r[0].transcript).join(" ").trim());
  rec.onerror = (e) => {
    if (e.error !== "aborted") error = ERRORS[e.error] || "Dictation stopped unexpectedly.";
  };
  rec.onend = () => onEnd(error);
  try {
    rec.start();
  } catch {
    onEnd("Dictation could not start. Try again.");
  }
  return () => rec.stop();
}
