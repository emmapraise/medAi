from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.agent.state import GraphState
from app.agent.nodes import (
    generate_query_node,
    retrieve_node,
    grade_documents_node,
    rewrite_query_node,
    generate_answer_node,
    grade_generation_node,
)

def route_after_query(state: GraphState) -> str:
    if state.get("is_conversational"):
        return END
    return "retrieve"

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

def build_crag_workflow(memory_saver: MemorySaver):
    builder = StateGraph(GraphState)

    builder.add_node("generate_query", generate_query_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("grade_documents", grade_documents_node)
    builder.add_node("rewrite_query", rewrite_query_node)
    builder.add_node("generate_answer", generate_answer_node)
    builder.add_node("grade_generation", grade_generation_node)

    builder.add_edge(START, "generate_query")
    builder.add_conditional_edges("generate_query", route_after_query, {"retrieve": "retrieve", END: END})
    builder.add_edge("retrieve", "grade_documents")

    builder.add_conditional_edges("grade_documents", decide_to_generate, {"generate_answer": "generate_answer", "rewrite_query": "rewrite_query"})
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("generate_answer", "grade_generation")
    builder.add_conditional_edges("grade_generation", decide_to_finish, {END: END, "generate_answer": "generate_answer"})

    return builder.compile(checkpointer=memory_saver)
