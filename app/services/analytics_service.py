from typing import Dict, Any, List, Optional
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db import Base, engine, SessionLocal
from app.models import ConversationSession, RAGQueryLog

class AnalyticsService:
    def initialize_db(self):
        Base.metadata.create_all(bind=engine)
        print("[AnalyticsService] PostgreSQL Database tables verified & initialized.")

    def calculate_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        model = model_name.lower()
        if "gemini" in model:
            # Gemini 2.5 Flash: $0.075 / 1M input, $0.30 / 1M output
            prompt_cost = (prompt_tokens / 1_000_000) * 0.075
            completion_cost = (completion_tokens / 1_000_000) * 0.30
        else:
            # GPT-4o-mini: $0.15 / 1M input, $0.60 / 1M output
            prompt_cost = (prompt_tokens / 1_000_000) * 0.15
            completion_cost = (completion_tokens / 1_000_000) * 0.60
        return round(prompt_cost + completion_cost, 6)

    def log_query(
        self,
        session_id: str,
        question: str,
        generated_query: str,
        retrieved_docs_count: int,
        is_relevant: str,
        is_grounded: str,
        is_useful: str,
        turns_executed: int,
        execution_trace: List[str],
        answer: str,
        model_used: str,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0
    ) -> RAGQueryLog:
        db: Session = SessionLocal()
        try:
            total_tokens = prompt_tokens + completion_tokens
            cost = self.calculate_cost(model_used, prompt_tokens, completion_tokens)

            # Ensure Session exists
            session_obj = db.query(ConversationSession).filter(ConversationSession.session_id == session_id).first()
            if not session_obj:
                session_obj = ConversationSession(session_id=session_id)
                db.add(session_obj)
                db.flush()

            session_obj.total_queries += 1
            session_obj.total_tokens += total_tokens
            session_obj.total_cost_usd += cost
            session_obj.last_active_at = datetime.datetime.utcnow()

            log_entry = RAGQueryLog(
                session_id=session_id,
                question=question,
                generated_query=generated_query,
                retrieved_docs_count=retrieved_docs_count,
                is_relevant=is_relevant,
                is_grounded=is_grounded,
                is_useful=is_useful,
                turns_executed=turns_executed,
                execution_trace=execution_trace,
                answer=answer,
                model_used=model_used,
                latency_ms=round(latency_ms, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=cost
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
            print(f"[AnalyticsService] Query logged to PostgreSQL (id={log_entry.id}, latency={latency_ms:.1f}ms, cost=${cost:.6f}).")
            return log_entry
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsService Error] Failed to log to PostgreSQL: {e}")
            raise e
        finally:
            db.close()

    def get_summary(self) -> Dict[str, Any]:
        db: Session = SessionLocal()
        try:
            total_queries = db.query(func.count(RAGQueryLog.id)).scalar() or 0
            total_sessions = db.query(func.count(ConversationSession.session_id)).scalar() or 0
            avg_latency = db.query(func.avg(RAGQueryLog.latency_ms)).scalar() or 0.0
            total_tokens = db.query(func.sum(RAGQueryLog.total_tokens)).scalar() or 0
            total_cost = db.query(func.sum(RAGQueryLog.estimated_cost_usd)).scalar() or 0.0

            relevant_count = db.query(func.count(RAGQueryLog.id)).filter(RAGQueryLog.is_relevant == "yes").scalar() or 0
            grounded_count = db.query(func.count(RAGQueryLog.id)).filter(RAGQueryLog.is_grounded == "yes").scalar() or 0
            useful_count = db.query(func.count(RAGQueryLog.id)).filter(RAGQueryLog.is_useful == "yes").scalar() or 0

            relevance_rate = round((relevant_count / total_queries * 100), 1) if total_queries > 0 else 0.0
            groundedness_rate = round((grounded_count / total_queries * 100), 1) if total_queries > 0 else 0.0
            usefulness_rate = round((useful_count / total_queries * 100), 1) if total_queries > 0 else 0.0
            avg_cost_per_query = round((total_cost / total_queries), 6) if total_queries > 0 else 0.0

            return {
                "total_queries": total_queries,
                "total_sessions": total_sessions,
                "avg_latency_ms": round(avg_latency, 2),
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 6),
                "avg_cost_per_query_usd": avg_cost_per_query,
                "document_relevance_rate_pct": relevance_rate,
                "groundedness_accuracy_rate_pct": groundedness_rate,
                "usefulness_rate_pct": usefulness_rate
            }
        finally:
            db.close()

analytics_service = AnalyticsService()
