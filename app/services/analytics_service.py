from typing import Dict, Any, List, Optional
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, text, inspect
from app.db import Base, engine, SessionLocal
from app.models import ConversationSession, RAGQueryLog

class AnalyticsService:
    def initialize_db(self):
        Base.metadata.create_all(bind=engine)
        try:
            with engine.connect() as conn:
                url_str = str(engine.url).lower()
                if "postgresql" in url_str:
                    conn.execute(text("ALTER TABLE rag_query_logs ADD COLUMN IF NOT EXISTS user_feedback VARCHAR;"))
                    conn.execute(text("ALTER TABLE rag_query_logs ADD COLUMN IF NOT EXISTS feedback_comment TEXT;"))
                    conn.commit()
                else:
                    inspector = inspect(engine)
                    existing_cols = [col["name"] for col in inspector.get_columns("rag_query_logs")]
                    if "user_feedback" not in existing_cols:
                        conn.execute(text("ALTER TABLE rag_query_logs ADD COLUMN user_feedback VARCHAR;"))
                    if "feedback_comment" not in existing_cols:
                        conn.execute(text("ALTER TABLE rag_query_logs ADD COLUMN feedback_comment TEXT;"))
                    conn.commit()
        except Exception as e:
            print(f"[AnalyticsService] Column migration check notice: {e}")
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
        latency_seconds: float,
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
                latency_seconds=round(latency_seconds, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=cost
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
            print(f"[AnalyticsService] Query logged to PostgreSQL (id={log_entry.id}, latency={latency_seconds:.2f}s, cost=${cost:.6f}).")
            return log_entry
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsService Error] Failed to log to PostgreSQL: {e}")
            raise e
        finally:
            db.close()

    def record_feedback(self, log_id: int, feedback: str, comment: Optional[str] = None) -> bool:
        db: Session = SessionLocal()
        try:
            log_entry = db.query(RAGQueryLog).filter(RAGQueryLog.id == log_id).first()
            if not log_entry:
                return False
            log_entry.user_feedback = feedback
            if comment:
                log_entry.feedback_comment = comment
            db.commit()
            print(f"[AnalyticsService] User feedback '{feedback}' recorded for log_id={log_id}.")
            return True
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsService Error] Failed to record feedback: {e}")
            raise e
        finally:
            db.close()

    def get_summary(self) -> Dict[str, Any]:
        db: Session = SessionLocal()
        try:
            total_queries = db.query(func.count(RAGQueryLog.id)).scalar() or 0
            total_sessions = db.query(func.count(ConversationSession.session_id)).scalar() or 0
            avg_latency = db.query(func.avg(RAGQueryLog.latency_seconds)).scalar() or 0.0
            total_tokens = db.query(func.sum(RAGQueryLog.total_tokens)).scalar() or 0
            total_cost = db.query(func.sum(RAGQueryLog.estimated_cost_usd)).scalar() or 0.0

            relevant_count = db.query(func.count(RAGQueryLog.id)).filter(RAGQueryLog.is_relevant == "yes").scalar() or 0
            grounded_count = db.query(func.count(RAGQueryLog.id)).filter(RAGQueryLog.is_grounded == "yes").scalar() or 0
            useful_count = db.query(func.count(RAGQueryLog.id)).filter(RAGQueryLog.is_useful == "yes").scalar() or 0

            positive_feedback = db.query(func.count(RAGQueryLog.id)).filter(RAGQueryLog.user_feedback == "positive").scalar() or 0
            negative_feedback = db.query(func.count(RAGQueryLog.id)).filter(RAGQueryLog.user_feedback == "negative").scalar() or 0
            total_feedback = positive_feedback + negative_feedback

            relevance_rate = round((relevant_count / total_queries * 100), 1) if total_queries > 0 else 0.0
            groundedness_rate = round((grounded_count / total_queries * 100), 1) if total_queries > 0 else 0.0
            usefulness_rate = round((useful_count / total_queries * 100), 1) if total_queries > 0 else 0.0
            satisfaction_rate = round((positive_feedback / total_feedback * 100), 1) if total_feedback > 0 else 100.0
            avg_cost_per_query = round((total_cost / total_queries), 6) if total_queries > 0 else 0.0

            return {
                "total_queries": total_queries,
                "total_sessions": total_sessions,
                "avg_latency_seconds": round(avg_latency, 2),
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 6),
                "avg_cost_per_query_usd": avg_cost_per_query,
                "document_relevance_rate_pct": relevance_rate,
                "groundedness_accuracy_rate_pct": groundedness_rate,
                "usefulness_rate_pct": usefulness_rate,
                "positive_feedback_count": positive_feedback,
                "negative_feedback_count": negative_feedback,
                "user_satisfaction_rate_pct": satisfaction_rate
            }
        finally:
            db.close()

analytics_service = AnalyticsService()
