"""Router-controlled syllabus graph (agent_v2).

Flow:

    entry -> router ─┬─▶ info_gather ──▶ router
                     ├─▶ planner     ──▶ router
                     ├─▶ advance     ──▶ router
                     ├─▶ writer_(lesson|activity) ──▶ critic
                     │                                │
                     │        pass ──▶ persist ──▶ router
                     │        fail & attempts<max ──▶ writer
                     │        fail & attempts>=max ──▶ escalate ──▶ router
                     └─▶ promote ──▶ END
"""
from __future__ import annotations
import logging

from langgraph.graph import StateGraph, END

from agent.checkpointer import get_checkpointer
from agent_v2.state import AgentStateV2
from agent_v2.router import route_after_router, route_after_critic, advance_indices
from agent_v2.info_gather import info_gather_node
from agent_v2.planner import planner_node
from agent_v2.writer import writer_lesson_node, writer_activity_node
from agent_v2.critic import critic_node
from agent_v2.persist import persist_node, escalate_node, promote_node

logger = logging.getLogger(__name__)


async def router_passthrough(state):
    """Router is just a branch dispatcher. We attach it as a node so conditional
    edges have a source; the node itself is a no-op."""
    return {}


async def advance_node(state):
    return advance_indices(state)


def build_graph_v2():
    g = StateGraph(AgentStateV2)
    g.add_node("router", router_passthrough)
    g.add_node("info_gather", info_gather_node)
    g.add_node("planner", planner_node)
    g.add_node("advance", advance_node)
    g.add_node("writer_lesson", writer_lesson_node)
    g.add_node("writer_activity", writer_activity_node)
    g.add_node("critic", critic_node)
    g.add_node("persist", persist_node)
    g.add_node("escalate", escalate_node)
    g.add_node("promote", promote_node)

    g.set_entry_point("router")

    g.add_conditional_edges("router", route_after_router, {
        "info_gather": "info_gather",
        "planner": "planner",
        "advance": "advance",
        "writer_lesson": "writer_lesson",
        "writer_activity": "writer_activity",
        "promote": "promote",
    })
    g.add_edge("info_gather", "router")
    g.add_edge("planner", "router")
    g.add_edge("advance", "router")
    g.add_edge("writer_lesson", "critic")
    g.add_edge("writer_activity", "critic")
    g.add_conditional_edges("critic", route_after_critic, {
        "writer_lesson": "writer_lesson",
        "writer_activity": "writer_activity",
        "persist": "persist",
        "escalate": "escalate",
    })
    g.add_edge("persist", "router")
    g.add_edge("escalate", "router")
    g.add_edge("promote", END)

    cp = get_checkpointer()
    return g.compile(checkpointer=cp) if cp is not None else g.compile()


graph = build_graph_v2()
