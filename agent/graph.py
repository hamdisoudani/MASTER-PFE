"""LangGraph state machine for Syllabus AI with Python tool routing."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .nodes import chat_node, PYTHON_TOOL_NAMES
from .tools import PYTHON_TOOLS


def _route_after_chat(state: AgentState) -> str:
    """Route to tools node if the LLM made calls for Python-side tools, else END."""
    messages = state.get("messages") or []
    if not messages:
        return END
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    has_python_call = any(tc.get("name") in PYTHON_TOOL_NAMES for tc in tool_calls)
    return "tools" if has_python_call else END


_builder = StateGraph(AgentState)
_builder.add_node("chat", chat_node)
_builder.add_node("tools", ToolNode(PYTHON_TOOLS))

_builder.set_entry_point("chat")
_builder.add_conditional_edges(
    "chat",
    _route_after_chat,
    {"tools": "tools", END: END},
)
_builder.add_edge("tools", "chat")

memory = MemorySaver()
graph = _builder.compile(checkpointer=memory)
