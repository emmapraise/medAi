import { useEffect, useRef, useState } from "react";
import { Check, Copy, Share2, X } from "lucide-react";
import { createShare, getShare, stopShare } from "../lib/api";

const linkFor = (token) => `${window.location.origin}/s/${token}`;

/** Creates, copies and switches off the read-only link to this conversation. Nothing is shared until "Create link" is pressed. */
export default function ShareSheet({ sessionId, onClose }) {
  const ref = useRef(null);
  const [token, setToken] = useState(undefined); // undefined: still asking, null: not shared, string: shared
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    getShare(sessionId)
      .then((d) => setToken(d.token))
      .catch(() => setError("Couldn't check this conversation. Close this and try again."));
    return () => dialog.open && dialog.close();
  }, [sessionId]);

  const change = async (action) => {
    setBusy(true);
    setError("");
    try {
      setToken((await action(sessionId)).token);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(linkFor(token));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Couldn't copy. Select the link and copy it by hand.");
    }
  };

  const canShare = typeof navigator.share === "function";
  const send = () => navigator.share({ title: "MediQA conversation", url: linkFor(token) }).catch(() => {}); // cancelling the system sheet is not an error

  return (
    <dialog ref={ref} className="sheet" data-size="small" aria-labelledby="share-title" onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}>
      <header className="sheet-head">
        <button type="button" className="tool" onClick={onClose} autoFocus>
          <X size={20} aria-hidden="true" /> Close
        </button>
        <h2 id="share-title">Share conversation</h2>
      </header>

      <div className="sheet-body share-body">
        {token === undefined && !error && <p role="status">Checking…</p>}

        {token === null && (
          <>
            <p>
              Anyone who has the link can read this whole conversation: your questions, the answers and their sources.
              They can't add to it or change it, and you can stop sharing at any time.
            </p>
            <p>Don't share it if it contains anything private.</p>
            <button type="button" className="primary" disabled={busy} onClick={() => change(createShare)}>Create link</button>
          </>
        )}

        {token && (
          <>
            <label htmlFor="share-link">Link to this conversation</label>
            <input id="share-link" className="share-link" readOnly value={linkFor(token)} onFocus={(e) => e.target.select()} />
            <div className="share-actions">
              <button type="button" className="primary" onClick={copy}>
                {copied ? <Check size={18} aria-hidden="true" /> : <Copy size={18} aria-hidden="true" />}
                <span role="status">{copied ? "Copied" : "Copy link"}</span>
              </button>
              {canShare && (
                <button type="button" className="tool" onClick={send}>
                  <Share2 size={18} aria-hidden="true" /> Share…
                </button>
              )}
              <button type="button" className="tool danger" disabled={busy} onClick={() => change(stopShare)}>Stop sharing</button>
            </div>
            <p className="fine">Stopping makes this link stop working for good. Sharing again makes a new link.</p>
          </>
        )}

        {error && <p className="inline-note is-error" role="alert">{error}</p>}
      </div>
    </dialog>
  );
}
