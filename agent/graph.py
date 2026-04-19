from __future__ import annotations
import json
import logging

from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agent.nodes import chat_node, frontend_tool_node, route_after_chat
from agent.state import AgentState
from agent.tools import PYTHON_TOOLS

logger = logging.getLogger(__name__)


def _tool_error_handler(exc: Exception) -> str:
    """Ported from open-swe's ToolErrorMiddleware — never let a tool exception
    kill the run; surface it as a structured ToolMessage instead."""
    logger.exception("tool execution raised: %s", exc)
    return json.dumps({"error": str(exc), "type": exc.__class__.__name__})


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("chat_node", chat_node)
    g.add_node("tools", ToolNode(PYTHON_TOOLS, handle_tool_errors=_tool_error_handler))
    g.add_node("frontend_tools", frontend_tool_node)
    g.add_conditional_edges(
        "chat_node",
        route_after_chat,
        {"tools": "tools", "frontend_tools": "frontend_tools", "end": END},
    )
    g.add_edge("tools", "chat_node")
    g.add_edge("frontend_tools", "chat_node")
    g.set_entry_point("chat_node")
    return g.compile()


graph = build_graph()
