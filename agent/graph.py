from __future__ import annotations
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agent.state import AgentState
from agent.nodes import chat_node, frontend_tool_node, route_after_chat
from agent.tools import PYTHON_TOOLS


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("chat_node", chat_node)
    g.add_node("tools", ToolNode(PYTHON_TOOLS))
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
