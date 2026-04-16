"""LangGraph state machine for Syllabus AI."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .nodes import chat_node, PYTHON_TOOL_NAMES
from .tools import PYTHON_TOOLS


def _should_continue(state: AgentState) -> str:
    """
    Route after chat_node.

    With parallel_tool_calls=False the LLM emits at most ONE tool call per
    AIMessage, so the mixed-type case (frontend + Python in same message)
    never arises under normal operation. This routing handles both cases
    cleanly regardless:

      - No tool calls          -> END  (plain assistant reply)
      - Any frontend tool call -> END  (AG-UI dispatches to client via
                                        useFrontendTool; CopilotKit injects
                                        result before next graph turn)
      - Python-only tool calls -> "tools"  (ToolNode executes server-side)
    """
    messages = state.get("messages") or []
    if not messages:
        return END
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return END

    has_frontend_call = any(
        tc.get("name") not in PYTHON_TOOL_NAMES for tc in tool_calls
    )
    return END if has_frontend_call else "tools"


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
    return builder.compile(checkpointer=checkpointer)
