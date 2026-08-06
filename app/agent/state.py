from typing import List, Dict, Any, TypedDict

class GraphState(TypedDict):
    question: str
    query: str
    documents: List[Dict[str, Any]]
    generation: str
    retry_count: int
    is_relevant: str
    is_grounded: str
    is_useful: str
    execution_trace: List[str]
    history: List[Dict[str, str]]
    prompt_tokens: int
    completion_tokens: int
    fast_path: bool
    is_conversational: bool
