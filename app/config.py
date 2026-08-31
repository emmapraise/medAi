import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Medical QA Bot API"
    VERSION: str = "1.0.0"

    # Environment: "development", "test", "production"
    APP_ENV: str = os.getenv("APP_ENV", "development")

    # Qdrant Configuration
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", 6333))
    QDRANT_URL: str = os.getenv("QDRANT_URL", f"http://{os.getenv('QDRANT_HOST', 'localhost')}:{os.getenv('QDRANT_PORT', 6333)}")
    QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY", None)
    COLLECTION_NAME: str = "medical_knowledge_base_hybrid"

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
