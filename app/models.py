import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base

class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    session_id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    total_queries = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)

    logs = relationship("RAGQueryLog", back_populates="session", cascade="all, delete-orphan")

class RAGQueryLog(Base):
    __tablename__ = "rag_query_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String, ForeignKey("conversation_sessions.session_id"), index=True)
    question = Column(Text, nullable=False)
    generated_query = Column(Text, nullable=True)
    retrieved_docs_count = Column(Integer, default=0)
    is_relevant = Column(String, default="unknown")
    is_grounded = Column(String, default="unknown")
    is_useful = Column(String, default="unknown")
    turns_executed = Column(Integer, default=1)
    execution_trace = Column(JSON, nullable=True)
    answer = Column(Text, nullable=True)
    model_used = Column(String, nullable=False)
    latency_seconds = Column(Float, default=0.0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("ConversationSession", back_populates="logs")
