import os

from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Medical QA Bot API"
    VERSION: str = "1.0.0"

    # Environment: "development", "test", "production"
    APP_ENV: str = os.getenv("APP_ENV", "development")

    # Security
    # Comma-separated list of allowed browser origins. Empty = same-origin only.
    CORS_ORIGINS: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    # Protects admin endpoints (ingest, query logs, cache controls). Required in production.
    ADMIN_API_KEY: str | None = os.getenv("ADMIN_API_KEY")
    # Number of trusted reverse proxies in front of the app (Cloud Run = 1).
    # The client IP is taken from X-Forwarded-For counting from the right.
    TRUSTED_PROXY_COUNT: int = int(os.getenv("TRUSTED_PROXY_COUNT", 1))
    # Directory that ingestion datasets must live in.
    DATASET_DIR: str = os.getenv("DATASET_DIR", "dataset")

    # Qdrant Configuration
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", 6333))
    QDRANT_URL: str = os.getenv("QDRANT_URL", f"http://{os.getenv('QDRANT_HOST', 'localhost')}:{os.getenv('QDRANT_PORT', 6333)}")
    QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY", None)
    COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "medical_knowledge_base_hybrid")

    # Embedding Models
    DENSE_MODEL_NAME: str = os.getenv("DENSE_MODEL_NAME", "emmapraise/pubmedbert-base-embeddings-onnx")
    SPARSE_MODEL_NAME: str = "Qdrant/bm25"
    DENSE_VECTOR_SIZE: int = 768

    # LLM API Settings (Gemini & OpenAI)
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")

    # Langfuse Observability & Tracing Configuration
    LANGFUSE_PUBLIC_KEY: str | None = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY: str | None = os.getenv("LANGFUSE_SECRET_KEY")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"

    # Rate Limiting Configuration (In-Memory Sliding Window)
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")
    RATE_LIMIT_QA_TIMES: int = int(os.getenv("RATE_LIMIT_QA_TIMES", 5))
    RATE_LIMIT_QA_SECONDS: int = int(os.getenv("RATE_LIMIT_QA_SECONDS", 60))
    RATE_LIMIT_SEARCH_TIMES: int = int(os.getenv("RATE_LIMIT_SEARCH_TIMES", 30))
    RATE_LIMIT_SEARCH_SECONDS: int = int(os.getenv("RATE_LIMIT_SEARCH_SECONDS", 60))
    RATE_LIMIT_INGEST_TIMES: int = int(os.getenv("RATE_LIMIT_INGEST_TIMES", 3))
    RATE_LIMIT_INGEST_SECONDS: int = int(os.getenv("RATE_LIMIT_INGEST_SECONDS", 60))
    RATE_LIMIT_ANALYTICS_TIMES: int = int(os.getenv("RATE_LIMIT_ANALYTICS_TIMES", 60))
    RATE_LIMIT_ANALYTICS_SECONDS: int = int(os.getenv("RATE_LIMIT_ANALYTICS_SECONDS", 60))
    RATE_LIMIT_HEALTH_TIMES: int = int(os.getenv("RATE_LIMIT_HEALTH_TIMES", 120))
    RATE_LIMIT_HEALTH_SECONDS: int = int(os.getenv("RATE_LIMIT_HEALTH_SECONDS", 60))

    # In-Memory Caching Configuration (Zero Redis)
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() in ("true", "1", "yes")
    CACHE_QA_TTL: int = int(os.getenv("CACHE_QA_TTL", 3600))  # 1 hour
    CACHE_QA_MAX_SIZE: int = int(os.getenv("CACHE_QA_MAX_SIZE", 1000))
    CACHE_SEARCH_TTL: int = int(os.getenv("CACHE_SEARCH_TTL", 1800))  # 30 minutes
    CACHE_SEARCH_MAX_SIZE: int = int(os.getenv("CACHE_SEARCH_MAX_SIZE", 2000))
    CACHE_ANALYTICS_TTL: int = int(os.getenv("CACHE_ANALYTICS_TTL", 20))  # 20 seconds

    @property
    def LANGFUSE_ENABLED(self) -> bool:
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def LANGFUSE_TAGS(self) -> list[str]:
        """Base tags applied to every Langfuse trace, including environment."""
        return ["medical-qa", "crag", self.APP_ENV]

settings = Settings()
