from __future__ import annotations
import json
import logging
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agent.checkpointer import get_checkpointer
from agent.nodes import (
    chat_node,
    critic_node,
    frontend_tool_node,
    route_after_chat,
    route_after_critic,
    route_after_frontend_tools,
)
from agent.state import AgentState
from agent.tools import PYTHON_TOOLS, PYTHON_TOOL_NAMES

logger = logging.getLogger(__name__)
logger.info("server-side tools (python + curriculum-mcp): %s", sorted(PYTHON_TOOL_NAMES))

def _tool_error_handler(exc: Exception) -> str:
    logger.exception("tool execution raised: %s", exc)
    return json.dumps({"error": str(exc), "type": exc.__class__.__name__})

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("chat_node", chat_node)
    g.add_node("tools", ToolNode(PYTHON_TOOLS, handle_tool_errors=_tool_error_handler))
    g.add_node("frontend_tools", frontend_tool_node)
    g.add_node("critic_node", critic_node)

    g.add_conditional_edges(
        "chat_node",
        route_after_chat,
        {"tools": "tools", "frontend_tools": "frontend_tools", "end": END},
    )
    g.add_edge("tools", "chat_node")
    g.add_conditional_edges(
        "frontend_tools",
        route_after_frontend_tools,
        {"critic_node": "critic_node", "chat_node": "chat_node"},
    )
    g.add_conditional_edges(
        "critic_node",
        route_after_critic,
        {"chat_node": "chat_node", "end": END},
    )
    g.set_entry_point("chat_node")

    cp = get_checkpointer()
    if cp is not None:
        return g.compile(checkpointer=cp)
    return g.compile()

graph = build_graph()
