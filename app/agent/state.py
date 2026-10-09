from enum import Enum
from typing import Any, TypedDict


class NodeName(str, Enum):
    GENERATE_QUERY = "generate_query"
    RETRIEVE = "retrieve"
    GRADE_DOCUMENTS = "grade_documents"
    REWRITE_QUERY = "rewrite_query"
    GENERATE_ANSWER = "generate_answer"
    GRADE_GENERATION = "grade_generation"

class GraphState(TypedDict):
    question: str
    query: str
    documents: list[dict[str, Any]]
    generation: str
    retry_count: int
    is_relevant: str
    is_grounded: str
    is_useful: str
    execution_trace: list[str]
    history: list[dict[str, str]]
    prompt_tokens: int
    completion_tokens: int
    fast_path: bool
    is_conversational: bool
