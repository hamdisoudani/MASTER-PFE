from __future__ import annotations
import json
import logging

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agent.checkpointer import get_checkpointer
from agent.nodes import (
    chat_node,
    critic_node,
    frontend_tool_node,
    plan_router,
    route_after_chat,
    route_after_critic,
    route_after_frontend_tools,
    route_after_python_tools,
    tools_post_hook,
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
    # Runs after `tools` to (a) extract a plan when submit_plan was called,
    # and (b) surface draft* lesson mutations into `last_authored_lesson`
    # so the critic fires for the classic syllabus_agent path — which it
    # used to skip because the critic only watched frontend mutations.
    g.add_node("tools_post_hook", tools_post_hook)
    g.add_node("frontend_tools", frontend_tool_node)
    g.add_node("critic_node", critic_node)
    # Deterministic plan advancement: marks the current plan step, moves
    # the cursor, and injects the next-lesson brief. When the plan is
    # empty the node is a no-op and the graph behaves exactly like the
    # classic ReAct loop.
    g.add_node("plan_router", plan_router)

    g.add_conditional_edges(
        "chat_node",
        route_after_chat,
        {"tools": "tools", "frontend_tools": "frontend_tools", "end": END},
    )
    g.add_edge("tools", "tools_post_hook")
    g.add_conditional_edges(
        "tools_post_hook",
        route_after_python_tools,
        {
            "critic_node": "critic_node",
            "plan_router": "plan_router",
            "chat_node": "chat_node",
        },
    )
    g.add_conditional_edges(
        "frontend_tools",
        route_after_frontend_tools,
        {"critic_node": "critic_node", "chat_node": "chat_node"},
    )
    g.add_edge("critic_node", "plan_router")
    g.add_conditional_edges(
        "plan_router",
        route_after_critic,
        {"chat_node": "chat_node", "end": END},
    )
    g.set_entry_point("chat_node")

    cp = get_checkpointer()
    if cp is not None:
        return g.compile(checkpointer=cp)
    return g.compile()


graph = build_graph()
