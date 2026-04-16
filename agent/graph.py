from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.state import AgentState
from agent.nodes import chat_node, tools_node


def _should_continue(state: AgentState):
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def build_graph(checkpointer: BaseCheckpointSaver):
    """Compile the agent graph with the supplied checkpointer."""
    builder = StateGraph(AgentState)
    builder.add_node("chat", chat_node)
    builder.add_node("tools", tools_node)
    builder.set_entry_point("chat")
    builder.add_conditional_edges(
        "chat", _should_continue, {"tools": "tools", END: END}
    )
    builder.add_edge("tools", "chat")
    compiled = builder.compile(checkpointer=checkpointer)
    # Raise the recursion ceiling -- complex syllabi can take 100+ steps
    return compiled.with_config({"recursion_limit": 150})
