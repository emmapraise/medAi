import logging
import os

import pandas as pd
from fastembed import SparseTextEmbedding
from langfuse import observe
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.schemas import SearchResultItem

logger = logging.getLogger(__name__)

class SearchEngineService:
    def __init__(self):
        self.client: QdrantClient | None = None
        self.dense_model: SentenceTransformer | None = None
        self.sparse_model: SparseTextEmbedding | None = None

    def initialize(self):
        # CPU only (Cloud Run has no GPU); avoids importing torch just to detect one.
        device = "cpu"
        logger.info(f"[SearchEngine] Initializing using device: {device}")

        # Qdrant client setup
        try:
            self.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, check_compatibility=False, timeout=5)
            self.client.get_collections()
            logger.info(f"[SearchEngine] Connected to Qdrant Vector Server at {settings.QDRANT_URL}")
        except Exception as e:
            logger.warning(f"[SearchEngine] Standalone Qdrant server unreachable ({e}). Falling back to :memory:")
            self.client = QdrantClient(":memory:")

        # PubMedBERT ONNX Dense model — use minimal ONNX session for low memory footprint
        model_target = "models/pubmedbert-onnx" if os.path.isdir("models/pubmedbert-onnx") else settings.DENSE_MODEL_NAME
        logger.info(f"[SearchEngine] Loading ONNX Dense Model from: {model_target}...")
        try:
            import onnxruntime as ort
            # Restrict ONNX to 1 inter-op and 2 intra-op threads to save memory & CPU
            session_opts = ort.SessionOptions()
            session_opts.intra_op_num_threads = 2
            session_opts.inter_op_num_threads = 1
            session_opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            # graph_optimization_level BASIC saves ~100MB vs EXTENDED
            session_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC

            self.dense_model = SentenceTransformer(
                model_target,
                backend="onnx",
                model_kwargs={
                    "provider": "CPUExecutionProvider",
                    "session_options": session_opts,
                }
            )
        except Exception as onnx_err:
            logger.warning(f"[SearchEngine] ONNX loading notice ({onnx_err}), attempting standard loader...")
            self.dense_model = SentenceTransformer(model_target, device=device)

        # FastEmbed BM25 Sparse model — lazy threads to reduce memory spike
        logger.info("[SearchEngine] Loading FastEmbed BM25 Sparse Vectorizer (Qdrant/bm25)...")
        self.sparse_model = SparseTextEmbedding(model_name=settings.SPARSE_MODEL_NAME, threads=1)

        # Auto-ingest dataset if collection does not exist
        cols = [c.name for c in self.client.get_collections().collections]
        if settings.COLLECTION_NAME not in cols:
            logger.info(f"[SearchEngine] Collection '{settings.COLLECTION_NAME}' missing.")
            if os.path.exists("dataset/medquad.csv"):
                logger.info("[SearchEngine] Auto-ingesting dataset...")
                try:
                    self.ingest_dataset()
                except Exception as ie:
                    logger.warning(f"[SearchEngine] Auto-ingestion warning: {ie}")
            else:
                logger.info("[SearchEngine] 'dataset/medquad.csv' not present in container (using existing remote Qdrant collection).")

        logger.info("[SearchEngine] Search Engine Service ready.")

    def encode_sparse(self, text: str) -> models.SparseVector:
        embed = list(self.sparse_model.embed([str(text)]))[0]
        return models.SparseVector(
            indices=embed.indices.tolist(),
            values=embed.values.tolist()
        )

    @observe(as_type="retriever", name="qdrant-hybrid-search")
    def hybrid_search(self, query_text: str, top_k: int = 5) -> list[SearchResultItem]:
        if not self.client or not self.dense_model or not self.sparse_model:
            logger.info("[SearchEngine] Client uninitialized. Running initialize()...")
            self.initialize()

        cols = [c.name for c in self.client.get_collections().collections]
        if settings.COLLECTION_NAME not in cols:
            logger.info("[SearchEngine] Collection missing during search. Auto-ingesting...")
            self.ingest_dataset()

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
        logger.info(f"[SearchEngine] Generating dense embeddings for {len(texts)} documents...")
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
        logger.info(f"[SearchEngine] Upserting {len(points)} records into Qdrant...")
        for i in range(0, len(points), upload_batch):
            self.client.upsert(collection_name=settings.COLLECTION_NAME, points=points[i : i + upload_batch])

        logger.info(f"[SearchEngine] Dataset ingestion complete! Total points: {len(points)}")
        return len(points)

search_engine = SearchEngineService()
