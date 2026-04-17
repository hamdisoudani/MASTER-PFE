"""LangGraph state machine for Syllabus AI."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from .state import AgentState
from .nodes import chat_node, python_tools_node, PYTHON_TOOL_NAMES


def _should_continue(state: AgentState) -> str:
    messages = state.get("messages") or []
    if not messages:
        return END
    last       = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return END
    has_frontend = any(tc.get("name") not in PYTHON_TOOL_NAMES for tc in tool_calls)
    return END if has_frontend else "tools"


def build_graph(checkpointer: BaseCheckpointSaver):
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
