from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.agent.state import GraphState, NodeName
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
    return NodeName.RETRIEVE.value

def decide_to_generate(state: GraphState) -> str:
    if state["is_relevant"] == "yes" or state.get("retry_count", 0) >= 2:
        return NodeName.GENERATE_ANSWER.value
    return NodeName.REWRITE_QUERY.value

def decide_to_finish(state: GraphState) -> str:
    if state["is_grounded"] == "yes" and state["is_useful"] == "yes":
        return END
    elif state.get("retry_count", 0) >= 2:
        return END
    return NodeName.GENERATE_ANSWER.value

def build_crag_workflow(memory_saver: MemorySaver):
    builder = StateGraph(GraphState)

    builder.add_node(NodeName.GENERATE_QUERY.value, generate_query_node)
    builder.add_node(NodeName.RETRIEVE.value, retrieve_node)
    builder.add_node(NodeName.GRADE_DOCUMENTS.value, grade_documents_node)
    builder.add_node(NodeName.REWRITE_QUERY.value, rewrite_query_node)
    builder.add_node(NodeName.GENERATE_ANSWER.value, generate_answer_node)
    builder.add_node(NodeName.GRADE_GENERATION.value, grade_generation_node)

    builder.add_edge(START, NodeName.GENERATE_QUERY.value)
    builder.add_conditional_edges(
        NodeName.GENERATE_QUERY.value,
        route_after_query,
        {NodeName.RETRIEVE.value: NodeName.RETRIEVE.value, END: END}
    )
    builder.add_edge(NodeName.RETRIEVE.value, NodeName.GRADE_DOCUMENTS.value)

    builder.add_conditional_edges(
        NodeName.GRADE_DOCUMENTS.value,
        decide_to_generate,
        {
            NodeName.GENERATE_ANSWER.value: NodeName.GENERATE_ANSWER.value,
            NodeName.REWRITE_QUERY.value: NodeName.REWRITE_QUERY.value
        }
    )
    builder.add_edge(NodeName.REWRITE_QUERY.value, NodeName.RETRIEVE.value)
    builder.add_edge(NodeName.GENERATE_ANSWER.value, NodeName.GRADE_GENERATION.value)
    builder.add_conditional_edges(
        NodeName.GRADE_GENERATION.value,
        decide_to_finish,
        {
            END: END,
            NodeName.GENERATE_ANSWER.value: NodeName.GENERATE_ANSWER.value
        }
    )

    return builder.compile(checkpointer=memory_saver)
