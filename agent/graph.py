"""LangGraph state machine for Syllabus AI."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .nodes import chat_node, PYTHON_TOOL_NAMES
from .tools import PYTHON_TOOLS


def _should_continue(state: AgentState) -> str:
    """
    Route after chat_node:
      - No tool calls          -> END  (plain assistant reply)
      - Has Python tool calls  -> "tools"  (server-side execution)
      - Frontend-only calls    -> END  (AG-UI / CopilotKit handles execute
                                       callbacks on the client; results are
                                       injected back before the next turn)
    """
    messages = state.get("messages") or []
    if not messages:
        return END
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    has_python_call = any(tc.get("name") in PYTHON_TOOL_NAMES for tc in tool_calls)
    return "tools" if has_python_call else END


def build_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(AgentState)
    builder.add_node("chat", chat_node)
    builder.add_node("tools", ToolNode(PYTHON_TOOLS))
    builder.set_entry_point("chat")
    builder.add_conditional_edges(
        "chat",
        _should_continue,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "chat")
    # recursion_limit is set via LangGraphAGUIAgent(config=...) in main.py
    return builder.compile(checkpointer=checkpointer)
