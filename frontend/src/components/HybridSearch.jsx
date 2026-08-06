import React, { useState } from "react";
import { Search, BookOpen, Database, Sparkles } from "lucide-react";

export default function HybridSearch() {
  const [query, setQuery] = useState("Symptoms of Glaucoma");
  const [topK, setTopK] = useState(5);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const res = await fetch("/api/v1/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query, top_k: parseInt(topK, 10) })
      });
      const data = await res.json();
      setResults(data.results || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="search-sandbox">
      <div className="chart-card glass" style={{ marginBottom: "24px" }}>
        <h2 style={{ fontSize: "18px", marginBottom: "8px", display: "flex", alignItems: "center", gap: "10px" }}>
          <BookOpen color="#00f2fe" /> Medical Literature & Journal Search
        </h2>
        <p style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "20px" }}>
          Search PubMedBERT medical documents directly using AI semantic search and keyphrase matching.
        </p>

        <form onSubmit={handleSearch} style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <div style={{ flex: 1, display: "flex", alignItems: "center", background: "var(--bg-dark)", padding: "10px 16px", borderRadius: "30px", border: "1px solid var(--border-subtle)" }}>
            <Search size={18} color="var(--text-muted)" style={{ marginRight: "10px" }} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ background: "transparent", border: "none", outline: "none", color: "#fff", width: "100%" }}
              placeholder="Search medical terms or conditions..."
            />
          </div>
          <select value={topK} onChange={(e) => setTopK(e.target.value)} style={{ background: "var(--bg-dark)", color: "#fff", border: "1px solid var(--border-subtle)", padding: "10px 16px", borderRadius: "20px" }}>
            <option value={3}>Top 3</option>
            <option value={5}>Top 5</option>
            <option value={10}>Top 10</option>
          </select>
          <button type="submit" className="btn-primary">Search Medical Index</button>
        </form>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
          <p>Searching medical journals and clinical references...</p>
        </div>
      ) : results.length > 0 ? (
        <div style={{ display: "grid", gap: "16px" }}>
          {results.map((item, idx) => (
            <div key={idx} className="chart-card glass" style={{ borderLeft: "4px solid var(--accent-cyan)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px", fontSize: "12px", color: "var(--accent-cyan)", fontWeight: 700 }}>
                <span>Relevance Match: {(item.score * 100).toFixed(1)}% | Reference #{idx + 1}</span>
                <span>Source: {item.source}</span>
              </div>
              <h4 style={{ fontSize: "14px", marginBottom: "6px" }}>Category: {item.focus_area}</h4>
              <p style={{ fontSize: "13px", color: "var(--text-main)", marginBottom: "6px" }}><strong>Question:</strong> {item.question}</p>
              <p style={{ fontSize: "13px", color: "var(--text-muted)" }}><strong>Clinical Answer:</strong> {item.answer}</p>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
          <Database size={36} style={{ marginBottom: "12px", color: "var(--accent-cyan)" }} />
          <p>Type a medical condition above to explore clinical search results.</p>
        </div>
      )}
    </div>
  );
}
