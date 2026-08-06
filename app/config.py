import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Medical QA Bot API"
    VERSION: str = "1.0.0"
    
    # Qdrant Configuration
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", 6333))
    QDRANT_URL: str = os.getenv("QDRANT_URL", f"http://{QDRANT_HOST}:{QDRANT_PORT}")
    QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY", None)
    COLLECTION_NAME: str = "medical_knowledge_base_hybrid"
    
    # Embedding Models
    DENSE_MODEL_NAME: str = "NeuML/pubmedbert-base-embeddings"
    SPARSE_MODEL_NAME: str = "Qdrant/bm25"
    DENSE_VECTOR_SIZE: int = 768
    
    # LLM API Settings (Gemini & OpenAI)
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    DEFAULT_MODEL: str = "gemini-2.5-flash"

settings = Settings()
