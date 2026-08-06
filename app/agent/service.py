import time
from typing import Dict, Any, Optional
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.agent.llm_client import llm_client
from app.agent.workflow import build_crag_workflow
from app.services.analytics_service import analytics_service

class MedicalAgentService:
    def __init__(self):
        self.graph = None
        self.memory = MemorySaver()

    def initialize(self):
        llm_client.initialize()
        analytics_service.initialize_db()
        self.graph = build_crag_workflow(self.memory)
        print("[MedicalAgent] Modular LangGraph CRAG Workflow compiled successfully.")

    def run_qa(self, question: str, session_id: str = "default_session", model: Optional[str] = None, max_turns: int = 5) -> Dict[str, Any]:
        if self.graph is None:
            print("[MedicalAgent] Graph uninitialized. Running initialize()...")
            self.initialize()

        start_time = time.perf_counter()
        config = {"configurable": {"thread_id": session_id}}
        
        existing_state = self.graph.get_state(config)
        history = []
        if existing_state and existing_state.values:
            prev_history = existing_state.values.get("history", [])
            prev_question = existing_state.values.get("question")
            prev_answer = existing_state.values.get("generation")
            
            history = list(prev_history)
            if prev_question and prev_answer:
                history.append({"role": "user", "content": prev_question})
                history.append({"role": "assistant", "content": prev_answer})

        initial_state = {
            "question": question,
            "retry_count": 0,
            "execution_trace": [],
            "history": history,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "fast_path": False
        }
        
        final_state = self.graph.invoke(initial_state, config=config)
        end_time = time.perf_counter()
        latency_seconds = end_time - start_time

        model_name = model or settings.DEFAULT_MODEL
        p_tokens = final_state.get("prompt_tokens", 0)
        c_tokens = final_state.get("completion_tokens", 0)
        
        # Log query to PostgreSQL
        db_log = analytics_service.log_query(
            session_id=session_id,
            question=question,
            generated_query=final_state.get("query", ""),
            retrieved_docs_count=len(final_state.get("documents", [])),
            is_relevant=final_state.get("is_relevant", "unknown"),
            is_grounded=final_state.get("is_grounded", "unknown"),
            is_useful=final_state.get("is_useful", "unknown"),
            turns_executed=final_state.get("retry_count", 0) + 1,
            execution_trace=final_state.get("execution_trace", []),
            answer=final_state.get("generation", ""),
            model_used=model_name,
            latency_seconds=latency_seconds,
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens
        )
        
        return {
            "answer": final_state.get("generation", "Could not generate a validated answer."),
            "generated_query": final_state.get("query", ""),
            "is_relevant": final_state.get("is_relevant", "unknown"),
            "is_grounded": final_state.get("is_grounded", "unknown"),
            "is_useful": final_state.get("is_useful", "unknown"),
            "execution_trace": final_state.get("execution_trace", []),
            "session_id": session_id,
            "latency_seconds": round(latency_seconds, 2),
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": p_tokens + c_tokens,
            "estimated_cost_usd": db_log.estimated_cost_usd,
            "turns_executed": final_state.get("retry_count", 0) + 1
        }
