from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.state import AgentState
from agent.nodes import chat_node, tools_node, PYTHON_TOOL_NAMES


def _should_continue(state: AgentState):
    """
    Route to pre_tools only when there are backend (Python) tool calls in the
    last message. Frontend-only calls go to END — AG-UI handles them via
    execute hooks on the client side.
    """
    last = state["messages"][-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return END

    has_backend = any(tc.get("name") in PYTHON_TOOL_NAMES for tc in last.tool_calls)
    return "pre_tools" if has_backend else END


async def pre_tools_node(state: AgentState) -> dict:
    """
    Inject synthetic ToolMessages for any FRONTEND tool calls in the last AIMessage.
    This prevents the LLM from looping when the same AIMessage contains both a
    backend tool call (handled by tools_node) and a frontend tool call (handled by
    AG-UI on the client side). Without this, the LLM would see a dangling tool call
    with no result and keep re-calling it, hitting the recursion limit.
    """
    last = state["messages"][-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return {}

    synthetic_messages = [
        ToolMessage(
            content="acknowledged",
            tool_call_id=tc.get("id", ""),
            name=tc.get("name", ""),
        )
        for tc in last.tool_calls
        if tc.get("name", "") not in PYTHON_TOOL_NAMES
    ]

    return {"messages": synthetic_messages} if synthetic_messages else {}


def build_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(AgentState)
    builder.add_node("chat", chat_node)
    builder.add_node("pre_tools", pre_tools_node)
    builder.add_node("tools", tools_node)
    builder.set_entry_point("chat")
    builder.add_conditional_edges(
        "chat",
        _should_continue,
        {"pre_tools": "pre_tools", END: END},
    )
    builder.add_edge("pre_tools", "tools")
    builder.add_edge("tools", "chat")
    # Note: recursion_limit is set on LangGraphAGUIAgent.config in main.py
    return builder.compile(checkpointer=checkpointer)
