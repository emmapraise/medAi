import concurrent.futures
from typing import Dict, Any
from app.agent.state import GraphState
from app.agent.llm_client import llm_client
from app.services.search_service import search_engine

# Node 1: Formulate Search Query with Greeting & Fast-Path Detection
def generate_query_node(state: GraphState) -> Dict[str, Any]:
    question = state["question"]
    history = state.get("history", [])
    trace = list(state.get("execution_trace", []))
    p_tok = state.get("prompt_tokens", 0)
    c_tok = state.get("completion_tokens", 0)
    
    # 1. Greeting & Conversational Check (Bypass RAG for greetings)
    clean_q = question.strip().lower()
    greeting_triggers = ["hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening", "how are you", "who are you", "what can you do", "thank you", "thanks", "bye", "goodbye"]
    is_greeting = any(clean_q == g or clean_q.startswith(g + " ") or clean_q.startswith(g + ",") or clean_q.startswith(g + "!") or clean_q.startswith(g + "?") for g in greeting_triggers) and len(clean_q.split()) <= 7
    
    if is_greeting:
        prompt_conv = f"User greeting/statement: '{question}'\nYou are MediQA Bot, an evidence-based AI Medical Assistant. Respond warmly, professionally, and concisely in 2-3 sentences. Invite the user to ask medical or health questions."
        ans, model, p, c = llm_client.invoke(prompt_conv, temperature=0.5)
        
        log_msg = "[Action: Conversational Greeting] Direct response without RAG search."
        print(f"[LangGraph Trace] {log_msg}")
        trace.append(log_msg)
        return {
            "generation": ans,
            "is_conversational": True,
            "is_relevant": "yes",
            "is_grounded": "yes",
            "is_useful": "yes",
            "execution_trace": trace,
            "prompt_tokens": p_tok + p,
            "completion_tokens": c_tok + c
        }

    # Check for short affirmative response (e.g. "yes", "sure", "tell me more", "correct", "okay")
    affirmative_triggers = ["yes", "sure", "yeah", "yep", "ok", "okay", "please", "tell me more", "go ahead", "of course", "correct", "absolutely", "i would", "yes please"]
    is_affirmative = any(clean_q == a or clean_q.startswith(a + " ") or clean_q.startswith(a + ",") or clean_q.startswith(a + ".") or clean_q.startswith(a + "!") for a in affirmative_triggers) and len(clean_q.split()) <= 6

    # 2. Speculative Fast-Path Retrieval (Only if not a short affirmative response)
    if not is_affirmative:
        try:
            speculative_docs = search_engine.hybrid_search(query_text=question, top_k=3)
            if speculative_docs and len(speculative_docs) > 0 and speculative_docs[0].score >= 0.65:
                query = question
                log_msg = f"[Action: Generate Query] Fast-path speculative match found (score={speculative_docs[0].score:.3f}). Skipping LLM query reformulation."
                print(f"[LangGraph Trace] {log_msg}")
                trace.append(log_msg)
                return {
                    "query": query,
                    "execution_trace": trace,
                    "retry_count": state.get("retry_count", 0),
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "fast_path": True,
                    "is_conversational": False
                }
        except Exception as se:
            print(f"[MedicalAgent] Speculative search skipped: {se}")

    history_str = ""
    if history:
        history_str = "Conversation History:\n" + "\n".join([f"{h['role']}: {h['content']}" for h in history]) + "\n\n"

    if is_affirmative and history:
        last_assistant_msg = ""
        for h in reversed(history):
            if h.get("role") in ["assistant", "bot"]:
                last_assistant_msg = h.get("content", "")
                break

        prompt = f"{history_str}Last Assistant Offer/Question: '{last_assistant_msg}'\nUser Response: '{question}'\n\nThe user responded YES/AFFIRMATIVE to the assistant's previous question or topic offer. Formulate a short standalone medical search query using clear medical terms to search for the specific topic offered in the assistant's question. Output ONLY the query text without preamble."
    else:
        prompt = f"{history_str}User Question: '{question}'\nFormulate a short standalone medical search query using clear medical terms. Output ONLY the query text without any preamble."

    raw_res, model, p, c = llm_client.invoke(prompt, temperature=0.1)
    
    # Sanitize generated query from preambles or quotes
    query = raw_res.strip().strip('"').strip("'").split("\n")[0]
    for prefix in ["query:", "search query:", "medical query:", "here is the search query:", "here is:", "standalone query:"]:
        if query.lower().startswith(prefix):
            query = query[len(prefix):].strip()
            
    # Fallback to original user question if query formulation returned empty or invalid string
    if not query or len(query) < 2:
        query = question
    
    log_msg = f"[Action: Generate Query] Formulated query: '{query}'"
    print(f"[LangGraph Trace] {log_msg}")
    trace.append(log_msg)
    
    return {
        "query": query,
        "execution_trace": trace,
        "retry_count": state.get("retry_count", 0),
        "prompt_tokens": p_tok + p,
        "completion_tokens": c_tok + c,
        "fast_path": False,
        "is_conversational": False
    }

# Node 2: Retrieve Documents (Qdrant Search)
def retrieve_node(state: GraphState) -> Dict[str, Any]:
    query = state["query"]
    trace = list(state.get("execution_trace", []))
    
    try:
        results = search_engine.hybrid_search(query_text=query, top_k=5)
        docs = [r.model_dump() for r in results]
    except Exception as se:
        print(f"[MedicalAgent] Search engine error: {se}")
        docs = []
    
    log_msg = f"[Action: Retrieve] Retrieved {len(docs)} passages from Qdrant for query: '{query}'"
    print(f"[LangGraph Trace] {log_msg}")
    trace.append(log_msg)
    
    return {"documents": docs, "execution_trace": trace}

# Node 3: Grade Documents Relevance
def grade_documents_node(state: GraphState) -> Dict[str, Any]:
    question = state["question"]
    docs = state["documents"]
    trace = list(state.get("execution_trace", []))
    p_tok = state.get("prompt_tokens", 0)
    c_tok = state.get("completion_tokens", 0)
    
    if not docs:
        log_msg = "[Action: Grade Documents] No passages found -> Relevance: NO"
        print(f"[LangGraph Trace] {log_msg}")
        trace.append(log_msg)
        return {"is_relevant": "no", "execution_trace": trace}
        
    doc_texts = "\n\n".join([f"Q: {d['question']}\nA: {d['answer']}" for d in docs])
    prompt = f"System: You are an expert medical grader. Determine if the retrieved medical context below is relevant to the question.\nQuestion: '{question}'\nContext:\n{doc_texts}\n\nIs the context relevant to answering the question? Reply strictly with a single word: YES or NO."
    
    raw_res, model, p, c = llm_client.invoke(prompt, temperature=0.0)
    is_rel = "yes" if "YES" in raw_res.upper() or "RELEVANT" in raw_res.upper() else "no"
    
    log_msg = f"[Action: Grade Documents] Relevance Grade: {is_rel.upper()}"
    print(f"[LangGraph Trace] {log_msg}")
    trace.append(log_msg)
    
    return {
        "is_relevant": is_rel,
        "execution_trace": trace,
        "prompt_tokens": p_tok + p,
        "completion_tokens": c_tok + c
    }

# Node 4: Rewrite Query
def rewrite_query_node(state: GraphState) -> Dict[str, Any]:
    question = state["question"]
    current_retry = state.get("retry_count", 0) + 1
    trace = list(state.get("execution_trace", []))
    p_tok = state.get("prompt_tokens", 0)
    c_tok = state.get("completion_tokens", 0)
    
    prompt = f"Rewrite '{question}' into an improved medical query using alternative key terminology. Output ONLY the query text without preamble."
    raw_res, model, p, c = llm_client.invoke(prompt, temperature=0.2)
    query = raw_res.strip().strip('"').split("\n")[0]
    
    log_msg = f"[Action: Rewrite Query #{current_retry}] Alternative query: '{query}'"
    print(f"[LangGraph Trace] {log_msg}")
    trace.append(log_msg)
    
    return {
        "query": query,
        "retry_count": current_retry,
        "execution_trace": trace,
        "prompt_tokens": p_tok + p,
        "completion_tokens": c_tok + c
    }

# Node 5: Generate Answer
def generate_answer_node(state: GraphState) -> Dict[str, Any]:
    question = state["question"]
    docs = state["documents"]
    history = state.get("history", [])
    trace = list(state.get("execution_trace", []))
    p_tok = state.get("prompt_tokens", 0)
    c_tok = state.get("completion_tokens", 0)
    
    history_str = ""
    if history:
        history_str = "Conversation History:\n" + "\n".join([f"{h['role']}: {h['content']}" for h in history]) + "\n\n"
        
    doc_context = "\n\n".join([f"Category: {d['focus_area']}\nQ: {d['question']}\nA: {d['answer']}" for d in docs])
    prompt = f"You are a knowledgeable and compassionate Medical QA Assistant.\n{history_str}Answer the user question based strictly on the retrieved medical context below.\n\nQuestion: {question}\n\nRetrieved Context:\n{doc_context}\n\nProvide a clear, accurate, evidence-based answer. Conclude by politely asking a follow-up offer question that the user can naturally answer with 'yes', 'sure', or 'correct' (for example: 'Would you like to know more about AIDS?' or 'Would you like to learn about available treatment options?'). Do NOT include headers or labels like '**Suggested follow-up question:**' or 'Follow-up question:'."
    
    res, model, p, c = llm_client.invoke(prompt, temperature=0.3)
    
    # Strip any explicit follow-up labels if generated by LLM
    for label in [
        "**Suggested follow-up question:**",
        "**Suggested Follow-up Question:**",
        "**Suggested follow up question:**",
        "Suggested follow-up question:",
        "Suggested Follow-up Question:",
        "Suggested follow up question:",
        "**Follow-up question:**",
        "**Follow-up Question:**",
        "Follow-up question:",
        "Follow-up Question:"
    ]:
        res = res.replace(label, "").strip()
    
    log_msg = f"[Action: Generate Answer] Synthesized candidate answer ({len(res)} chars)"
    print(f"[LangGraph Trace] {log_msg}")
    trace.append(log_msg)
    
    return {
        "generation": res,
        "execution_trace": trace,
        "prompt_tokens": p_tok + p,
        "completion_tokens": c_tok + c
    }

# Node 6: Grade Generation (Parallel Verification)
def grade_generation_node(state: GraphState) -> Dict[str, Any]:
    question = state["question"]
    generation = state["generation"]
    docs = state["documents"]
    trace = list(state.get("execution_trace", []))
    p_tok = state.get("prompt_tokens", 0)
    c_tok = state.get("completion_tokens", 0)
    
    doc_context = "\n\n".join([f"Q: {d['question']}\nA: {d['answer']}" for d in docs])
    
    prompt_grounded = f"System: Evaluate if the answer is grounded and supported by the context.\nContext:\n{doc_context}\nAnswer:\n{generation}\n\nIs the answer supported by the context? Reply strictly with a single word: YES or NO."
    prompt_useful = f"System: Evaluate if the answer addresses the user's question.\nUser Question: '{question}'\nAnswer:\n{generation}\n\nDoes the answer address the question? Reply strictly with a single word: YES or NO."

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_grounded = executor.submit(llm_client.invoke, prompt_grounded, None, 0.0)
        future_useful = executor.submit(llm_client.invoke, prompt_useful, None, 0.0)
        
        res_grounded, m1, p1, c1 = future_grounded.result()
        res_useful, m2, p2, c2 = future_useful.result()

    is_grounded = "yes" if "YES" in res_grounded.upper() or "SUPPORTED" in res_grounded.upper() else "no"
    is_useful = "yes" if "YES" in res_useful.upper() or "ADDRESSES" in res_useful.upper() else "no"
    
    log_msg = f"[Action: Grade Generation] Parallel Verification -> Grounded={is_grounded.upper()}, Useful={is_useful.upper()}"
    print(f"[LangGraph Trace] {log_msg}")
    trace.append(log_msg)
    
    return {
        "is_grounded": is_grounded,
        "is_useful": is_useful,
        "execution_trace": trace,
        "prompt_tokens": p_tok + p1 + p2,
        "completion_tokens": c_tok + c1 + c2
    }
