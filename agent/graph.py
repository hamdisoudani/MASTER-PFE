"""LangGraph state machine for Syllabus AI.

Key settings:
  recursion_limit = 150  — allows large syllabi with many chapters/lessons
  tools_node routes only Python-side tool calls back to chat_node
  Frontend tool calls (create_syllabus etc.) are handled by CopilotKit runtime
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .nodes import chat_node, PYTHON_TOOL_NAMES
from .tools import PYTHON_TOOLS


def _route_after_chat(state: AgentState) -> str:
    """Route to tools node if the LLM made Python-side tool calls, else END."""
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
_compiled = _builder.compile(checkpointer=memory)

# Set a high recursion limit so the agent can handle large syllabi
# (many chapters × many lessons × plan_tasks + update calls all count as steps)
graph = _compiled.with_config({"recursion_limit": 150})
