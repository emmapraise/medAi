import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { tidyQuestion } from "../lib/format";

const DISMISS_DRAG_PX = 100;

/**
 * The sources behind an answer. A modal <dialog>: focus is trapped, Esc closes, the page behind is inert.
 * Narrow screens get a bottom sheet (grabber, medium/large detents, swipe down to dismiss); wide screens a side panel.
 */
export default function SourceSheet({ cites, active, onClose }) {
  const ref = useRef(null);
  const drag = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    dialog.querySelector(`#src-${active}`)?.scrollIntoView({ block: "start" });
    return () => dialog.open && dialog.close();
  }, [active]);

  const toggleSize = () => {
    const d = ref.current;
    d.dataset.size = d.dataset.size === "large" ? "medium" : "large";
  };

  // Capture the pointer only once a real drag starts, otherwise it would swallow taps on the grabber.
  const onPointerDown = (e) => {
    if (e.target.closest("button:not(.grabber)")) return;
    drag.current = { y: e.clientY, captured: false };
  };
  const onPointerMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dy = e.clientY - d.y;
    if (!d.captured && Math.abs(dy) > 6) {
      e.currentTarget.setPointerCapture(e.pointerId);
      d.captured = true;
    }
    if (d.captured) ref.current.style.transform = `translateY(${Math.max(0, dy)}px)`;
  };
  const onPointerUp = (e) => {
    const d = drag.current;
    drag.current = null;
    if (!d?.captured) return;
    ref.current.style.transform = "";
    if (e.clientY - d.y > DISMISS_DRAG_PX) onClose();
  };

  return (
    <dialog
      ref={ref}
      className="sheet"
      data-size="medium"
      aria-labelledby="sheet-title"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      <header className="sheet-head" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}>
        <button type="button" className="grabber" onClick={toggleSize} aria-label="Resize sources panel" />
        <button type="button" className="tool" onClick={onClose} autoFocus>
          <X size={20} aria-hidden="true" /> Close
        </button>
        <h2 id="sheet-title">Sources</h2>
      </header>

      <div className="sheet-body">
        {cites.map((c) => (
          <article key={c.n} id={`src-${c.n}`} className={c.n === active ? "source is-active" : "source"}>
            <h3>
              <span className="source-n" aria-hidden="true">{c.n}</span>
              {tidyQuestion(c.question)}
            </h3>
            <p className="source-meta">{c.source} · {c.focus_area}</p>
            <p className="source-text">{c.passage}</p>
          </article>
        ))}
        <p className="fine">
          Excerpts from NIH-sourced pages in the MedQuAD collection. The answer's wording is written by AI from these
          passages, so check anything important with them or a clinician.
        </p>
      </div>
    </dialog>
  );
}
