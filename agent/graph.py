from __future__ import annotations
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from .state import AgentState
from .nodes import chat_node, search_node, scraper_node


def _build_search_subgraph() -> StateGraph::
    """
    Compiled sub-graph:  search_node → scraper_node → (exit to parent).

    After scraper_node finishes, control returns to 'chat_node' in the
    parent graph via the edge  search_subgraph → chat_node.
    """
    sg = StateGraph(AgentState)
    sg.add_node("search_node", search_node)
    sg.add_node("scraper_node", scraper_node)
    sg.add_edge("search_node", "scraper_node")
    sg.set_entry_point("search_node")
    sg.set_finish_point("scraper_node")
    return sg.compile()


def build_graph(checkpointer: BaseCheckpointSaver):
    """
    Main graph topology:

        [entry] chat_node
                 │
                 ┌─ plan tool calls?      "�� chat_node  (loop, state updated inline)
                 ┌─ pending search step? → search_subgraph
                 ├─ frontend tool calls? → END
                    text only?           → END

        search_subgraph (search_node → scraper_node)
                 L always              → chat_node  (LLM writes content with research)
    """
    search_subgraph = _build_search_subgraph()

    main = StateGraph(AgentState)
    main.add_node("chat_node", chat_node)
    main.add_node("search_subgraph", search_subgraph)

    # chat_node uses Command for routing — conditional_edges not needed
    # search_subgraph always returns control to chat_node
    main.add_edge("search_subgraph", "chat_node")

    main.set_entry_point("chat_node")

    return main.compile(checkpointer=checkpointer)
