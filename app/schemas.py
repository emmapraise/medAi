from typing import List, Optional
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    query: str = Field(..., description="Medical query text", example="What are the symptoms of Glaucoma?")
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
    results: List[SearchResultItem]

class AskRequest(BaseModel):
    question: str = Field(..., description="Medical question for the AI agent", example="How do I know if a baby has liver cancer?")
    session_id: Optional[str] = Field(default="default_session", description="Session ID for follow-up questions", example="patient_session_101")
    model: Optional[str] = Field(default="gemini-2.5-flash", description="LLM model name to use")
    max_turns: Optional[int] = Field(default=5, description="Maximum agent tool iterations", ge=1, le=10)

class AskResponse(BaseModel):
    question: str
    generated_query: str
    answer: str
    session_id: str
    is_relevant: str
    is_grounded: str
    is_useful: str
    execution_trace: List[str]
    model_used: str
    latency_seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    turns_executed: int
    trace_id: Optional[str] = None

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

class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., description="Langfuse trace ID", example="17a62465269b9427a8015c6aa8f58625")
    value: float = Field(..., description="Score value (1.0 for thumbs up/positive, 0.0 for thumbs down/negative)", example=1.0)
    name: Optional[str] = Field(default="user-feedback", description="Score metric name", example="user-feedback")
    comment: Optional[str] = Field(default=None, description="Optional user comment or reason")

class FeedbackResponse(BaseModel):
    status: str
    trace_id: str
    name: str
    value: float
