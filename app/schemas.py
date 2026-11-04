from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Medical query text", examples=["What are the symptoms of Glaucoma?"])
    top_k: int = Field(default=5, description="Number of top search results to retrieve", ge=1, le=50)

class SearchResultItem(BaseModel):
    score: float
    focus_area: str
    question: str
    answer: str
    source: str

class SearchResponse(BaseModel):
    query: str
    results_count: int
    results: list[SearchResultItem]
    cached: bool | None = False

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Medical question for the AI agent", examples=["How do I know if a baby has liver cancer?"])
    session_id: str | None = Field(default="default_session", pattern=r"^[A-Za-z0-9_-]{1,64}$", description="Session ID for follow-up questions", examples=["3f9c1c2e-5b7a-4a52-9e0d-6a1d7f0b2c11"])
    model: str | None = Field(default=None, description="LLM model name to use (defaults to gemini-2.5-flash)")
    max_turns: int | None = Field(default=5, description="Maximum agent tool iterations", ge=1, le=10)

class AskResponse(BaseModel):
    id: int | None = Field(default=None, description="Query log ID for user feedback tracking")
    question: str
    generated_query: str
    answer: str
    session_id: str
    is_relevant: str
    is_grounded: str
    is_useful: str
    execution_trace: list[str]
    model_used: str
    latency_seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    turns_executed: int
    trace_id: str | None = None
    cached: bool | None = False

# --- Analytics DB Feedback (thumbs up/down stored to PostgreSQL) ---
class AnalyticsFeedbackRequest(BaseModel):
    log_id: int = Field(..., description="Query log ID to record feedback for")
    feedback: Literal["positive", "negative"] = Field(..., description="Feedback value: 'positive' (thumbs up) or 'negative' (thumbs down)")
    comment: str | None = Field(default=None, max_length=1000, description="Optional user comment")

class AnalyticsFeedbackResponse(BaseModel):
    status: str
    log_id: int
    feedback: str

# --- Langfuse Score Feedback (trace-level scores sent to Langfuse) ---
class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., description="Langfuse trace ID", examples=["17a62465269b9427a8015c6aa8f58625"])
    value: float = Field(..., ge=0.0, le=1.0, description="Score value (1.0 thumbs up, 0.0 thumbs down)", examples=[1.0])
    name: str | None = Field(default="user-feedback", description="Score metric name", examples=["user-feedback"])
    comment: str | None = Field(default=None, description="Optional user comment or reason")

class FeedbackResponse(BaseModel):
    status: str
    trace_id: str
    name: str
    value: float

class IngestResponse(BaseModel):
    status: str
    records_ingested: int
    collection_name: str

class HealthResponse(BaseModel):
    status: str
    qdrant_connected: bool
    qdrant_url: str
    collection_exists: bool
    total_points: int

class CacheNamespaceStats(BaseModel):
    name: str
    current_size: int
    max_size: int
    default_ttl_seconds: int
    hits: int
    misses: int
    hit_ratio_percent: float
    evictions: int

class CacheStatsResponse(BaseModel):
    qa_cache: CacheNamespaceStats
    search_cache: CacheNamespaceStats
    analytics_cache: CacheNamespaceStats


