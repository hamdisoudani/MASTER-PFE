from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.state import AgentState
from agent.nodes import chat_node, tools_node, PYTHON_TOOL_NAMES


def _should_continue(state: AgentState):
    """
    Route to tools only for backend (Python) tool calls.
    Frontend tool calls are handled by AG-UI via execute hooks -- never reach tools_node.
    """
    last = state["messages"][-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return END

    has_backend = any(tc.get("name") in PYTHON_TOOL_NAMES for tc in last.tool_calls)
    return "tools" if has_backend else END


def build_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(AgentState)
    builder.add_node("chat", chat_node)
    builder.add_node("tools", tools_node)
    builder.set_entry_point("chat")
    builder.add_conditional_edges("chat", _should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "chat")
    compiled = builder.compile(checkpointer=checkpointer)
    return compiled.with_config({"recursion_limit": 150})
