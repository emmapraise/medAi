"""v2 retrieval: fastembed (ONNX, no torch) dense + BM25 sparse over chunked answers, RRF fusion.

    python -m app.services.search_v2          # (re)build the collection from dataset/medquad.csv
"""
import difflib
import os
import re
from collections import Counter
from pathlib import Path

import pandas as pd
from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models
from tqdm import tqdm

# Own env vars on purpose: v2 must never pick up the cloud QDRANT_URL from .env by accident.
QDRANT_URL = os.getenv("V2_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("V2_COLLECTION", "mediqa_v2")
DENSE_MODEL = os.getenv("V2_DENSE_MODEL", "BAAI/bge-small-en-v1.5")
CHUNK_WORDS = int(os.getenv("V2_CHUNK_WORDS", "150"))
QUESTION_ID_BASE = 10_000_000  # chunk point ids are 0..n; question points live above them
VOCAB_FILE =Path(__file__).with_name("vocab.txt")  # "word count" per line, built from the corpus by write_vocab()


def chunk(text: str, limit: int = CHUNK_WORDS) -> list[str]:
    """Split on sentence boundaries into ~limit-word pieces. Never returns an empty list."""
    out, cur, n = [], [], 0
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        w = len(sent.split())
        if cur and n + w > limit:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(sent)
        n += w
    out.append(" ".join(cur))
    return out


def write_vocab(csv_path: str = "dataset/medquad.csv") -> int:
    df = pd.read_csv(csv_path).fillna("")
    counts = Counter(w for t in (df["question"] + " " + df["answer"]) for w in re.findall(r"[a-z]+", str(t).lower()))
    VOCAB_FILE.write_text("\n".join(f"{w} {n}" for w, n in counts.most_common()) + "\n")
    return len(counts)


def load_vocab() -> Counter:
    if not VOCAB_FILE.exists():
        return Counter()
    return Counter({w: int(n) for w, n in (line.split() for line in VOCAB_FILE.read_text().splitlines())})


def fix_typos(query: str, vocab: Counter) -> str:
    """Replace words absent from the corpus with the closest well-attested corpus word. No vocab -> unchanged.
    shortcut: difflib over ~all common words per unknown word, fine at one query at a time; use rapidfuzz if it gets slow."""
    cands = [w for w, n in vocab.items() if n >= 3 and len(w) >= 5]
    def fix(m):
        w = m.group(0)
        if len(w) < 5 or not vocab or w.lower() in vocab:
            return w
        best = difflib.get_close_matches(w.lower(), cands, n=1, cutoff=0.8)
        return best[0] if best else w
    return re.sub(r"[A-Za-z]+", fix, query)


class SearchV2:
    def __init__(self):
        self.client = QdrantClient(url=QDRANT_URL, timeout=30)
        self.dense = TextEmbedding(DENSE_MODEL)
        self.sparse = SparseTextEmbedding("Qdrant/bm25")
        self.vocab = load_vocab()

    def ingest(self, csv_path: str = "dataset/medquad.csv", batch: int = 256, resume: bool = False) -> int:
        write_vocab(csv_path)
        df = pd.read_csv(csv_path)
        for col, default in (("question", ""), ("answer", ""), ("focus_area", "General"), ("source", "Unknown")):
            df[col] = df[col].fillna(default).astype(str)
        rows = [
            {"row_id": int(i), "question": r.question, "focus_area": r.focus_area, "source": r.source, "chunk": c}
            for i, r in df.iterrows()
            for c in chunk(r.answer)
        ]
        if resume and self.client.collection_exists(COLLECTION):
            start = self.client.count(COLLECTION).count  # each upsert is a whole batch, so this is a batch boundary
        else:
            start = 0
            dim = len(next(iter(self.dense.embed(["x"]))))
            if self.client.collection_exists(COLLECTION):
                self.client.delete_collection(COLLECTION)
            self.client.create_collection(
                COLLECTION,
                vectors_config={"dense": models.VectorParams(size=dim, distance=models.Distance.COSINE, on_disk=True)},
                sparse_vectors_config={"sparse": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=True))},
            )
        for s in tqdm(range(start, len(rows), batch), desc="ingest", unit="batch", mininterval=5):
            part = rows[s : s + batch]
            texts = [f"{r['question']}\n{r['chunk']}" for r in part]  # question first: carries the intent (symptoms/causes/...)
            dense = list(self.dense.embed(texts))
            sparse = list(self.sparse.embed(texts))
            self.client.upsert(COLLECTION, [
                models.PointStruct(
                    id=s + i,
                    vector={"dense": dense[i].tolist(), "sparse": models.SparseVector(indices=sparse[i].indices.tolist(), values=sparse[i].values.tolist())},
                    payload=r,
                )
                for i, r in enumerate(part)
            ])
        return len(rows) + self.add_question_points(csv_path)

    def add_question_points(self, csv_path: str = "dataset/medquad.csv", batch: int = 512) -> int:
        """One extra dense point per row, embedded from the question text alone, so a query like
        'can I pass X to my children' can match 'Is X inherited ?' on intent. Same collection; search()
        ranks them in their own list (kind filter) so they don't crowd out the chunk ranking."""
        self.client.create_payload_index(COLLECTION, "kind", models.PayloadSchemaType.KEYWORD)
        df = pd.read_csv(csv_path).fillna({"question": "", "answer": "", "focus_area": "General", "source": "Unknown"})
        self.client.delete(COLLECTION, models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="question"))])))
        for s in tqdm(range(0, len(df), batch), desc="questions", unit="batch", mininterval=5):
            part = df.iloc[s : s + batch]
            dense = list(self.dense.embed(part["question"].astype(str).tolist()))
            self.client.upsert(COLLECTION, [
                models.PointStruct(
                    id=QUESTION_ID_BASE + int(idx),
                    vector={"dense": dense[i].tolist()},
                    payload={"row_id": int(idx), "question": r.question, "focus_area": r.focus_area, "source": r.source,
                             "chunk": chunk(str(r.answer))[0], "kind": "question"},
                )
                for i, (idx, r) in enumerate(part.iterrows())
            ])
        return len(df)

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Top-k distinct answers (best chunk per MedQuAD row), best first."""
        return self.search_with_confidence(query, k)[0]

    def search_with_confidence(self, query: str, k: int = 5) -> tuple[list[dict], float]:
        """Same as search(), plus the best raw dense cosine for the query: RRF scores are rank-based,
        so only this tells the agent whether anything in the corpus is actually close."""
        query = fix_typos(query, self.vocab)
        d = next(iter(self.dense.query_embed(query))).tolist()
        sp = next(iter(self.sparse.query_embed(query)))
        pool = k * 4  # several chunks can come from one row; over-fetch then dedupe
        is_q = models.FieldCondition(key="kind", match=models.MatchValue(value="question"))
        res = self.client.query_points(
            COLLECTION,
            prefetch=[
                models.Prefetch(query=d, using="dense", limit=pool, filter=models.Filter(must_not=[is_q])),
                models.Prefetch(query=d, using="dense", limit=pool, filter=models.Filter(must=[is_q])),
                models.Prefetch(query=models.SparseVector(indices=sp.indices.tolist(), values=sp.values.tolist()), using="sparse", limit=pool),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=pool,
        )
        seen, out = set(), []
        for p in res.points:
            if p.payload["row_id"] in seen:
                continue
            seen.add(p.payload["row_id"])
            out.append({**p.payload, "score": p.score})
        top = self.client.query_points(COLLECTION, query=d, using="dense", limit=1).points
        return out[:k], (top[0].score if top else 0.0)


if __name__ == "__main__":
    import sys

    s = SearchV2()
    if "--questions" in sys.argv:
        print(f"added {s.add_question_points()} question points to {COLLECTION}")
    else:
        print(f"indexed {s.ingest(resume='--resume' in sys.argv)} points into {COLLECTION}")
