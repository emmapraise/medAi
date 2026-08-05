import os
import json
import re
from typing import List, Dict, Any, Optional, TypedDict
from dotenv import load_dotenv
from fastapi import HTTPException

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.services.search_service import search_engine

# =====================================================================
# LangGraph State Schema with Execution Tracing & Conversation History
# =====================================================================

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

# =====================================================================
# Medical Agent Service (LangGraph CRAG + MemorySaver + Fallback)
# =====================================================================

class MedicalAgentService:
    def __init__(self):
        self.llm: Optional[ChatOpenAI] = None
        self.fallback_llm: Optional[ChatOpenAI] = None
        self.graph = None
        self.memory = MemorySaver()

    def initialize(self):
        gemini_key = settings.GEMINI_API_KEY
        openai_key = settings.OPENAI_API_KEY

        if not gemini_key and not openai_key:
            raise RuntimeError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured.")

        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key

        if gemini_key:
            self.llm = ChatOpenAI(
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                model=settings.DEFAULT_MODEL
            )
            print(f"[MedicalAgent] Primary LLM: Gemini ({settings.DEFAULT_MODEL}).")
        
        if openai_key:
            self.fallback_llm = ChatOpenAI(
                api_key=openai_key,
                model="gpt-4o-mini"
            )
            print("[MedicalAgent] Fallback LLM: OpenAI (gpt-4o-mini).")
            if not self.llm:
                self.llm = self.fallback_llm

        self.build_graph()

    def invoke_llm(self, prompt: str) -> str:
        try:
            res = self.llm.invoke(prompt)
            return str(res.content).strip()
        except Exception as e:
            err_msg = str(e).lower()
            if ("429" in err_msg or "resource_exhausted" in err_msg or "rate" in err_msg) and self.fallback_llm and self.llm != self.fallback_llm:
                print("[MedicalAgent] Gemini rate limited (429). Falling back to OpenAI gpt-4o-mini...")
                res = self.fallback_llm.invoke(prompt)
                return str(res.content).strip()
            raise e

    def build_graph(self):
        # -------------------------------------------------------------
        # Node 1: Formulate Search Query (Context-Aware for Follow-ups)
        # -------------------------------------------------------------
        def generate_query_node(state: GraphState) -> Dict[str, Any]:
            question = state["question"]
            history = state.get("history", [])
            trace = list(state.get("execution_trace", []))
            
            history_str = ""
            if history:
                history_str = "Conversation History:\n" + "\n".join([f"{h['role']}: {h['content']}" for h in history]) + "\n\n"

            prompt = f"{history_str}User Question: '{question}'\nFormulate a standalone medical search query using clear medical terms. Output only the query text."
            raw_res = self.invoke_llm(prompt)
            query = raw_res.strip().strip('"')
            
            log_msg = f"[Action: Generate Query] Formulated search query: '{query}'"
            print(f"[LangGraph Trace] {log_msg}")
            trace.append(log_msg)
            
            return {"query": query, "execution_trace": trace, "retry_count": state.get("retry_count", 0)}

        # -------------------------------------------------------------
        # Node 2: Retrieve Documents (Qdrant Hybrid Search)
        # -------------------------------------------------------------
        def retrieve_node(state: GraphState) -> Dict[str, Any]:
            query = state["query"]
            trace = list(state.get("execution_trace", []))
            
            results = search_engine.hybrid_search(query_text=query, top_k=5)
            docs = [r.model_dump() for r in results]
            
            log_msg = f"[Action: Retrieve] Retrieved {len(docs)} passages from Qdrant for query: '{query}'"
            print(f"[LangGraph Trace] {log_msg}")
            trace.append(log_msg)
            
            return {"documents": docs, "execution_trace": trace}

        # -------------------------------------------------------------
        # Node 3: Grade Documents Relevance
        # -------------------------------------------------------------
        def grade_documents_node(state: GraphState) -> Dict[str, Any]:
            question = state["question"]
            docs = state["documents"]
            trace = list(state.get("execution_trace", []))
            
            if not docs:
                log_msg = "[Action: Grade Documents] No passages found -> Relevance: NO"
                print(f"[LangGraph Trace] {log_msg}")
                trace.append(log_msg)
                return {"is_relevant": "no", "execution_trace": trace}
                
            doc_texts = "\n\n".join([f"Q: {d['question']}\nA: {d['answer']}" for d in docs])
            prompt = f"Given question '{question}', evaluate if these medical passages contain relevant info:\n\n{doc_texts}\n\nRespond strictly 'YES' or 'NO'."
            raw_res = self.invoke_llm(prompt).upper()
            is_rel = "yes" if "YES" in raw_res else "no"
            
            log_msg = f"[Action: Grade Documents] Relevance Grade: {is_rel.upper()}"
            print(f"[LangGraph Trace] {log_msg}")
            trace.append(log_msg)
            
            return {"is_relevant": is_rel, "execution_trace": trace}

        # -------------------------------------------------------------
        # Node 4: Rewrite Query (if documents were irrelevant)
        # -------------------------------------------------------------
        def rewrite_query_node(state: GraphState) -> Dict[str, Any]:
            question = state["question"]
            current_retry = state.get("retry_count", 0) + 1
            trace = list(state.get("execution_trace", []))
            
            prompt = f"Rewrite '{question}' into an improved medical query using alternative key terminology."
            raw_res = self.invoke_llm(prompt)
            query = raw_res.strip().strip('"')
            
            log_msg = f"[Action: Rewrite Query #{current_retry}] Alternative query: '{query}'"
            print(f"[LangGraph Trace] {log_msg}")
            trace.append(log_msg)
            
            return {"query": query, "retry_count": current_retry, "execution_trace": trace}

        # -------------------------------------------------------------
        # Node 5: Generate Answer
        # -------------------------------------------------------------
        def generate_answer_node(state: GraphState) -> Dict[str, Any]:
            question = state["question"]
            docs = state["documents"]
            history = state.get("history", [])
            trace = list(state.get("execution_trace", []))
            
            history_str = ""
            if history:
                history_str = "Conversation History:\n" + "\n".join([f"{h['role']}: {h['content']}" for h in history]) + "\n\n"
                
            doc_context = "\n\n".join([f"Category: {d['focus_area']}\nQ: {d['question']}\nA: {d['answer']}" for d in docs])
            prompt = f"""
You are a knowledgeable and compassionate Medical QA Assistant.
{history_str}Answer the user question based strictly on the retrieved medical context below.

Question: {question}

Retrieved Context:
{doc_context}

Provide a clear, accurate, evidence-based answer. Conclude by asking if the user has follow-up questions:
"""
            res = self.invoke_llm(prompt)
            
            log_msg = f"[Action: Generate Answer] Synthesized candidate answer ({len(res)} chars)"
            print(f"[LangGraph Trace] {log_msg}")
            trace.append(log_msg)
            
            return {"generation": res, "execution_trace": trace}

        # -------------------------------------------------------------
        # Node 6: Grade Generation (Self-Correction & Hallucination Check)
        # -------------------------------------------------------------
        def grade_generation_node(state: GraphState) -> Dict[str, Any]:
            question = state["question"]
            generation = state["generation"]
            docs = state["documents"]
            trace = list(state.get("execution_trace", []))
            
            doc_context = "\n\n".join([f"Q: {d['question']}\nA: {d['answer']}" for d in docs])
            
            res_grounded = self.invoke_llm(f"Is this answer supported by context?\nContext: {doc_context}\nAnswer: {generation}\nRespond 'YES' or 'NO'.").upper()
            is_grounded = "yes" if "YES" in res_grounded else "no"
            
            res_useful = self.invoke_llm(f"Does this answer user question: '{question}'?\nAnswer: {generation}\nRespond 'YES' or 'NO'.").upper()
            is_useful = "yes" if "YES" in res_useful else "no"
            
            log_msg = f"[Action: Grade Generation] Grounded={is_grounded.upper()}, Useful={is_useful.upper()}"
            print(f"[LangGraph Trace] {log_msg}")
            trace.append(log_msg)
            
            return {"is_grounded": is_grounded, "is_useful": is_useful, "execution_trace": trace}

        # -------------------------------------------------------------
        # Conditional Edge Handlers
        # -------------------------------------------------------------
        def decide_to_generate(state: GraphState) -> str:
            if state["is_relevant"] == "yes" or state.get("retry_count", 0) >= 2:
                return "generate_answer"
            return "rewrite_query"

        def decide_to_finish(state: GraphState) -> str:
            if state["is_grounded"] == "yes" and state["is_useful"] == "yes":
                return END
            elif state.get("retry_count", 0) >= 2:
                return END
            return "generate_answer"

        # -------------------------------------------------------------
        # Graph Assembly & MemorySaver Checkpointer
        # -------------------------------------------------------------
        builder = StateGraph(GraphState)

        builder.add_node("generate_query", generate_query_node)
        builder.add_node("retrieve", retrieve_node)
        builder.add_node("grade_documents", grade_documents_node)
        builder.add_node("rewrite_query", rewrite_query_node)
        builder.add_node("generate_answer", generate_answer_node)
        builder.add_node("grade_generation", grade_generation_node)

        builder.add_edge(START, "generate_query")
        builder.add_edge("generate_query", "retrieve")
        builder.add_edge("retrieve", "grade_documents")

        builder.add_conditional_edges("grade_documents", decide_to_generate, {"generate_answer": "generate_answer", "rewrite_query": "rewrite_query"})
        builder.add_edge("rewrite_query", "retrieve")
        builder.add_edge("generate_answer", "grade_generation")
        builder.add_conditional_edges("grade_generation", decide_to_finish, {END: END, "generate_answer": "generate_answer"})

        self.graph = builder.compile(checkpointer=self.memory)
        print("[MedicalAgent] LangGraph Self-Corrective RAG with MemorySaver & LLM Fallback compiled successfully.")

    def run_qa(self, question: str, session_id: str = "default_session", model: Optional[str] = None, max_turns: int = 5) -> Dict[str, Any]:
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
            "history": history
        }
        
        final_state = self.graph.invoke(initial_state, config=config)
        
        return {
            "answer": final_state.get("generation", "Could not generate a validated answer."),
            "execution_trace": final_state.get("execution_trace", []),
            "session_id": session_id,
            "turns_executed": final_state.get("retry_count", 0) + 1
        }

agent_service = MedicalAgentService()
