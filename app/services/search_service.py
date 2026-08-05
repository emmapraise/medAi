import os
import torch
import pandas as pd
from typing import List, Optional
from fastapi import HTTPException

from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

from app.config import settings
from app.schemas import SearchResultItem

class SearchEngineService:
    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self.dense_model: Optional[SentenceTransformer] = None
        self.sparse_model: Optional[SparseTextEmbedding] = None

    def initialize(self):
        device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[SearchEngine] Initializing using device: {device}")

        # Qdrant client setup
        try:
            self.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, check_compatibility=False, timeout=5)
            self.client.get_collections()
            print(f"[SearchEngine] Connected to Qdrant Vector Server at {settings.QDRANT_URL}")
        except Exception as e:
            print(f"[SearchEngine] Standalone Qdrant server unreachable ({e}). Falling back to :memory:")
            self.client = QdrantClient(":memory:")

        # PubMedBERT Dense model setup
        print("[SearchEngine] Loading PubMedBERT Dense Model...")
        try:
            self.dense_model = SentenceTransformer(settings.DENSE_MODEL_NAME, device=device, local_files_only=True)
        except Exception:
            self.dense_model = SentenceTransformer(settings.DENSE_MODEL_NAME, device=device)

        # FastEmbed BM25 Sparse model setup
        print("[SearchEngine] Loading FastEmbed BM25 Sparse Vectorizer (Qdrant/bm25)...")
        self.sparse_model = SparseTextEmbedding(model_name=settings.SPARSE_MODEL_NAME)
        print("[SearchEngine] Search Engine Service ready.")

    def encode_sparse(self, text: str) -> models.SparseVector:
        embed = list(self.sparse_model.embed([str(text)]))[0]
        return models.SparseVector(
            indices=embed.indices.tolist(),
            values=embed.values.tolist()
        )

    def hybrid_search(self, query_text: str, top_k: int = 5) -> List[SearchResultItem]:
        cols = [c.name for c in self.client.get_collections().collections]
        if settings.COLLECTION_NAME not in cols:
            raise HTTPException(
                status_code=404, 
                detail=f"Collection '{settings.COLLECTION_NAME}' not found in Qdrant. Call POST /api/v1/ingest first."
            )

        query_dense = self.dense_model.encode(query_text, normalize_embeddings=True).tolist()
        query_sparse = self.encode_sparse(query_text)

        res = self.client.query_points(
            collection_name=settings.COLLECTION_NAME,
            prefetch=[
                models.Prefetch(query=query_dense, using="text-dense", limit=top_k * 3),
                models.Prefetch(query=query_sparse, using="text-sparse", limit=top_k * 3),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k
        )

        results = []
        for r in res.points:
            results.append(SearchResultItem(
                score=round(float(r.score), 4),
                focus_area=r.payload.get("focus_area", "General"),
                question=r.payload.get("question", ""),
                answer=r.payload.get("answer", ""),
                source=r.payload.get("source", "Unknown")
            ))
        return results

    def ingest_dataset(self, csv_path: str = "dataset/medquad.csv") -> int:
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Dataset file '{csv_path}' not found.")

        df = pd.read_csv(csv_path)
        df["question"] = df["question"].fillna("").astype(str)
        df["answer"] = df["answer"].fillna("").astype(str)
        df["focus_area"] = df["focus_area"].fillna("General").astype(str)
        df["source"] = df["source"].fillna("Unknown").astype(str)
        df["combined_text"] = df["question"] + " " + df["answer"]

        cols = [c.name for c in self.client.get_collections().collections]
        if settings.COLLECTION_NAME in cols:
            self.client.delete_collection(settings.COLLECTION_NAME)

        self.client.create_collection(
            collection_name=settings.COLLECTION_NAME,
            vectors_config={
                "text-dense": models.VectorParams(
                    size=settings.DENSE_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                    on_disk=True
                )
            },
            sparse_vectors_config={
                "text-sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=True)
                )
            }
        )

        texts = df["combined_text"].tolist()
        print(f"[SearchEngine] Generating dense embeddings for {len(texts)} documents...")
        dense_vectors = self.dense_model.encode(texts, batch_size=256, show_progress_bar=False, normalize_embeddings=True)

        points = []
        for idx, row in df.iterrows():
            points.append(models.PointStruct(
                id=idx,
                vector={
                    "text-dense": dense_vectors[idx].tolist(),
                    "text-sparse": self.encode_sparse(row["combined_text"])
                },
                payload={
                    "question": row["question"],
                    "answer": row["answer"],
                    "source": row["source"],
                    "focus_area": row["focus_area"]
                }
            ))

        upload_batch = 500
        print(f"[SearchEngine] Upserting {len(points)} records into Qdrant...")
        for i in range(0, len(points), upload_batch):
            self.client.upsert(collection_name=settings.COLLECTION_NAME, points=points[i : i + upload_batch])

        print(f"[SearchEngine] Dataset ingestion complete! Total points: {len(points)}")
        return len(points)

search_engine = SearchEngineService()
