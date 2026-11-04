import { useEffect, useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { getTopics } from "../lib/api";
import { tidyQuestion } from "../lib/format";

export default function Topics({ onAsk }) {
  const [q, setQ] = useState("");
  const [topics, setTopics] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      setError(false);
      getTopics(q.trim(), ctl.signal)
        .then(setTopics)
        .catch((err) => err.name !== "AbortError" && setError(true));
    }, q ? 250 : 0); // debounce typing, not the first load
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [q]);

  return (
    <div className="page">
      <div className="column">
        <h1 className="page-title">Topics</h1>
        <div className="search">
          <Search size={18} aria-hidden="true" />
          <label htmlFor="topic-search" className="sr-only">Search topics</label>
          <input id="topic-search" type="search" value={q} maxLength={60} placeholder="Search conditions and topics" autoComplete="off" onChange={(e) => setQ(e.target.value)} />
        </div>

        <h2 className="section-label">{q.trim() ? `Results for “${q.trim()}”` : "Common topics"}</h2>

        {error ? (
          <p className="empty" role="alert">Couldn't load topics. Check your connection, then change the search to try again.</p>
        ) : topics === null ? (
          <p className="empty" role="status">Loading topics…</p>
        ) : topics.length === 0 ? (
          <p className="empty">No topics match “{q.trim()}”. Try a shorter word, or ask your question in your own words on the Ask tab.</p>
        ) : (
          <ul className="topics">
            {topics.map((t) => (
              <li key={t.topic}>
                <details>
                  <summary>
                    <span>{t.topic}</span>
                    <ChevronRight size={18} aria-hidden="true" />
                  </summary>
                  <ul className="topic-questions">
                    {t.questions.map((question) => (
                      <li key={question}>
                        <button type="button" className="suggest" onClick={() => onAsk(tidyQuestion(question))}>{tidyQuestion(question)}</button>
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
