"""LangGraph state machine for Syllabus AI."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import ToolNode
from langchain_core.messages import ToolMessage

from .state import AgentState
from .nodes import chat_node, PYTHON_TOOL_NAMES
from .tools import PYTHON_TOOLS


def _should_continue(state: AgentState) -> str:
    """
    Route after chat_node:
      - No tool calls          -> END  (plain assistant reply)
      - Has Python tool calls  -> "pre_tools"  (inject synthetic frontend
                                  ToolMessages, then run ToolNode for Python)
      - Frontend-only calls    -> END  (AG-UI handles execute callbacks;
                                  CopilotKit injects results before next turn)
    """
    messages = state.get("messages") or []
    if not messages:
        return END
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    has_python_call = any(tc.get("name") in PYTHON_TOOL_NAMES for tc in tool_calls)
    return "pre_tools" if has_python_call else END


async def pre_tools_node(state: AgentState) -> dict:
    """Inject synthetic ToolMessage acknowledgements for frontend tool calls.

    When the LLM emits both Python and frontend tool calls in the same
    AIMessage, ToolNode only executes Python calls. Frontend calls must receive
    a synthetic ToolMessage or the LLM will loop waiting for results and
    eventually hit the recursion limit.

    This node runs before ToolNode and inserts one synthetic
    ToolMessage(content='acknowledged') per frontend tool call so the LLM's
    message history stays consistent.
    """
    messages = state.get("messages") or []
    if not messages:
        return {}
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []

    synthetic = [
        ToolMessage(
            content="acknowledged",
            tool_call_id=tc["id"],
            name=tc["name"],
        )
        for tc in tool_calls
        if tc.get("name") not in PYTHON_TOOL_NAMES
    ]
    return {"messages": synthetic} if synthetic else {}


def build_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(AgentState)
    builder.add_node("chat", chat_node)
    builder.add_node("pre_tools", pre_tools_node)
    builder.add_node("tools", ToolNode(PYTHON_TOOLS))
    builder.set_entry_point("chat")
    builder.add_conditional_edges(
        "chat",
        _should_continue,
        {"pre_tools": "pre_tools", END: END},
    )
    builder.add_edge("pre_tools", "tools")
    builder.add_edge("tools", "chat")
    # recursion_limit is set via LangGraphAGUIAgent(config=...) in main.py
    return builder.compile(checkpointer=checkpointer)
