from __future__ import annotations
from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes import chat_node, search_node, scraper_node, python_tools_node, route_after_chat


def _build_search_subgraph():
    sg = StateGraph(AgentState)
    sg.add_node("search_node", search_node)
    sg.add_node("scraper_node", scraper_node)
    sg.add_edge("search_node", "scraper_node")
    sg.set_entry_point("search_node")
    sg.set_finish_point("scraper_node")
    return sg.compile()


def build_graph():
    search_subgraph = _build_search_subgraph()
    main = StateGraph(AgentState)
    main.add_node("chat_node", chat_node)
    main.add_node("tools", python_tools_node)
    main.add_node("search_subgraph", search_subgraph)
    main.add_conditional_edges(
        "chat_node",
        route_after_chat,
        {"tools": "tools", "search_subgraph": "search_subgraph", "chat_node": "chat_node", "end": END},
    )
    main.add_edge("tools", "chat_node")
    main.add_edge("search_subgraph", "chat_node")
    main.set_entry_point("chat_node")
    return main.compile()


graph = build_graph()
