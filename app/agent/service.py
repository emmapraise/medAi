import time
from typing import Dict, Any, Optional
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.agent.llm_client import llm_client
from app.agent.workflow import build_crag_workflow
from app.services.analytics_service import analytics_service
from langfuse import observe, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

class MedicalAgentService:
    def __init__(self):
        self.graph = None
        self.memory = MemorySaver()

    def initialize(self):
        llm_client.initialize()
        analytics_service.initialize_db()
        self.graph = build_crag_workflow(self.memory)
        print("[MedicalAgent] Modular LangGraph CRAG Workflow compiled successfully.")

    @observe(as_type="agent", name="medical-qa-crag-agent")
    def run_qa(self, question: str, session_id: str = "default_session", model: Optional[str] = None, max_turns: int = 5) -> Dict[str, Any]:
        if self.graph is None:
            print("[MedicalAgent] Graph uninitialized. Running initialize()...")
            self.initialize()

        start_time = time.perf_counter()
        
        # Set clean, explicit trace input to avoid leaking unneeded parameters
        try:
            lf = get_client()
            lf.update_current_span(
                input={"question": question, "session_id": session_id, "model": model or settings.DEFAULT_MODEL}
            )
        except Exception:
            pass

        # Prepare Langfuse callbacks & metadata for LangGraph
        callbacks = []
        try:
            langfuse_handler = CallbackHandler()
            callbacks.append(langfuse_handler)
        except Exception:
            pass

        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": callbacks,
            "metadata": {
                "langfuse_session_id": session_id,
                "langfuse_tags": ["medical-qa", "crag", "production"],
                "model": model or settings.DEFAULT_MODEL,
                "question": question
            }
        }
        
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
        else:
            try:
                from app.db import SessionLocal
                from app.models import RAGQueryLog
                db = SessionLocal()
                try:
                    past_logs = db.query(RAGQueryLog).filter(RAGQueryLog.session_id == session_id).order_by(RAGQueryLog.id.asc()).all()
                    for plog in past_logs:
                        if plog.question and plog.answer:
                            history.append({"role": "user", "content": plog.question})
                            history.append({"role": "assistant", "content": plog.answer})
                finally:
                    db.close()
            except Exception as e:
                print(f"[MedicalAgent] DB history restoration notice: {e}")

        initial_state = {
            "question": question,
            "retry_count": 0,
            "execution_trace": [],
            "history": history,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "fast_path": False
        }
        
        # Propagate attributes across child observations
        with propagate_attributes(
            session_id=session_id,
            tags=["medical-qa", "crag", "production"],
            metadata={"model": model or settings.DEFAULT_MODEL}
        ):
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
        
        # Retrieve trace ID, set explicit output, and record automated evaluation scores
        trace_id = None
        try:
            lf = get_client()
            trace_id = lf.get_current_trace_id()
            is_rel = final_state.get("is_relevant", "unknown")
            is_grd = final_state.get("is_grounded", "unknown")
            is_use = final_state.get("is_useful", "unknown")
            
            lf.update_current_span(
                output={
                    "answer": final_state.get("generation", ""),
                    "is_relevant": is_rel,
                    "is_grounded": is_grd,
                    "is_useful": is_use,
                    "fast_path": final_state.get("fast_path", False),
                    "turns_executed": final_state.get("retry_count", 0) + 1
                },
                metadata={
                    "retrieved_docs_count": len(final_state.get("documents", [])),
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "estimated_cost_usd": db_log.estimated_cost_usd,
                    "latency_seconds": round(latency_seconds, 2)
                }
            )

            # Record Evaluator Scores in Langfuse
            if trace_id:
                if isinstance(is_rel, str) and is_rel.lower() in ["yes", "no"]:
                    lf.create_score(
                        trace_id=trace_id,
                        name="document-relevance",
                        value=1.0 if is_rel.lower() == "yes" else 0.0,
                        data_type="BOOLEAN",
                        comment=f"CRAG Document Relevance: {is_rel.upper()}"
                    )
                if isinstance(is_grd, str) and is_grd.lower() in ["yes", "no"]:
                    lf.create_score(
                        trace_id=trace_id,
                        name="groundedness",
                        value=1.0 if is_grd.lower() == "yes" else 0.0,
                        data_type="BOOLEAN",
                        comment=f"CRAG Groundedness (Hallucination Check): {is_grd.upper()}"
                    )
                if isinstance(is_use, str) and is_use.lower() in ["yes", "no"]:
                    lf.create_score(
                        trace_id=trace_id,
                        name="answer-usefulness",
                        value=1.0 if is_use.lower() == "yes" else 0.0,
                        data_type="BOOLEAN",
                        comment=f"CRAG Answer Usefulness & Alignment: {is_use.upper()}"
                    )
        except Exception as se:
            print(f"[MedicalAgent] Langfuse scoring notice: {se}")

        return {
            "id": db_log.id,
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
            "turns_executed": final_state.get("retry_count", 0) + 1,
            "trace_id": trace_id
        }

agent_service = MedicalAgentService()
