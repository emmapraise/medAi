import { useEffect, useState } from "react";
import Answer from "./Answer";
import SourceSheet from "./SourceSheet";
import { getShared } from "../lib/api";
import { fromHistory } from "../lib/entries";

/** What someone sees when they open a shared link: the conversation, read only, with its sources. */
export default function SharedView({ token }) {
  const [state, setState] = useState({ status: "loading", entries: [] });
  const [sheet, setSheet] = useState(null); // { entryId, n }

  useEffect(() => {
    document.title = "Shared conversation — MediQA";
    let active = true;
    getShared(token)
      .then((d) => active && setState({ status: "ok", entries: d.messages.map(fromHistory) }))
      .catch(() => active && setState({ status: "gone", entries: [] }));
    return () => {
      active = false;
    };
  }, [token]);

  const sheetEntry = sheet && state.entries.find((e) => e.id === sheet.entryId);

  return (
    <div className="shared">
      <header className="shared-head">
        <span className="brand">MediQA</span>
        <a className="tool" href="/">Ask your own question</a>
      </header>
      <main className="page">
        <div className="column">
          {state.status === "loading" && <p className="empty" role="status">Loading…</p>}
          {state.status === "gone" && (
            <section className="welcome">
              <h1>This link isn't active</h1>
              <p>The person who shared it may have stopped sharing, or the link was copied wrongly.</p>
            </section>
          )}
          {state.status === "ok" && (
            <>
              <p className="shared-note">
                A shared conversation. You can read it but not change it. Answers are AI-written from NIH sources, can
                make mistakes and aren't medical advice.
              </p>
              {state.entries.map((entry) => (
                <Answer key={entry.id} entry={entry} isLast={false} readOnly onCite={(e, n) => setSheet({ entryId: e.id, n })} />
              ))}
            </>
          )}
        </div>
      </main>
      {sheetEntry && <SourceSheet cites={sheetEntry.citations} active={sheet.n} onClose={() => setSheet(null)} />}
    </div>
  );
}
