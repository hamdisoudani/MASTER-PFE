from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.state import AgentState
from agent.nodes import chat_node, python_tools_node


def _should_continue(state: AgentState):
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def build_graph(checkpointer=None):
    if checkpointer is None:
        checkpointer = MemorySaver()

    builder = StateGraph(AgentState)
    builder.add_node("chat",  chat_node)
    builder.add_node("tools", python_tools_node)
    builder.set_entry_point("chat")
    builder.add_conditional_edges(
        "chat",
        _should_continue,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "chat")
    return builder.compile(checkpointer=checkpointer)
