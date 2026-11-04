"""Retrieval eval: hit@1, hit@5, MRR@10, latency, peak RSS.

    QDRANT_URL=http://localhost:6333 QDRANT_API_KEY= COLLECTION_NAME=mediqa_v1_baseline \
        python eval/run_retrieval.py v1

A retriever is `name -> (query, k) -> list[str]` of returned MedQuAD question texts, so any
engine (v1 now, v2 later) is scored the same way. Add v2 to RETRIEVERS in Phase 1.
"""
import json
import resource
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def v1():
    from app.services.search_service import search_engine

    search_engine.initialize()
    return lambda q, k: [r.question for r in search_engine.hybrid_search(q, top_k=k)]


def v2():
    from app.services.search_v2 import SearchV2

    s = SearchV2()
    return lambda q, k: [r["question"] for r in s.search(q, k)]


RETRIEVERS = {"v1": v1, "v2": v2}


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def main(name: str):
    search = RETRIEVERS[name]()
    cases = [c for c in map(json.loads, (ROOT / "eval" / "cases.jsonl").read_text().splitlines()) if c["gold"]]
    search(cases[0]["query"], 10)  # warm-up, excluded from timing

    by_kind = defaultdict(lambda: {"h1": 0, "h5": 0, "rr": 0.0, "n": 0})
    lat = []
    misses = []
    for c in cases:
        t = time.perf_counter()
        got = [norm(x) for x in search(c["query"], 10)]
        lat.append((time.perf_counter() - t) * 1000)
        rank = next((i + 1 for i, g in enumerate(got) if g == norm(c["gold"])), None)
        for key in (c["kind"], "ALL"):
            m = by_kind[key]
            m["n"] += 1
            m["h1"] += rank == 1
            m["h5"] += rank is not None and rank <= 5
            m["rr"] += 1 / rank if rank else 0.0
        if rank is None or rank > 5:
            misses.append({"id": c["id"], "query": c["query"], "gold": c["gold"], "top3": got[:3]})

    lat.sort()
    result = {
        "retriever": name,
        "cases": len(cases),
        "metrics": {
            k: {"hit@1": round(m["h1"] / m["n"], 3), "hit@5": round(m["h5"] / m["n"], 3), "mrr@10": round(m["rr"] / m["n"], 3), "n": m["n"]}
            for k, m in by_kind.items()
        },
        "latency_ms": {"p50": round(statistics.median(lat), 1), "p95": round(lat[int(len(lat) * 0.95) - 1], 1)},
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 0),  # bytes on macOS
        "misses": misses,
    }
    out = ROOT / "eval" / "results" / f"{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "misses"}, indent=2))
    print(f"{len(misses)} misses -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
