from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.state import AgentState
from agent.nodes import chat_node, tools_node, PYTHON_TOOL_NAMES


def _should_continue(state: AgentState):
    """
    Route after chat_node:
      - No tool calls           -> END  (plain assistant reply)
      - Has backend tool calls  -> "tools"  (server-side execution)
      - Frontend-only calls     -> END  (ag-ui handles execute callbacks;
                                        real results injected on next request)

    For mixed calls (backend + frontend in the same AIMessage), tools_node
    runs the Python tools and injects ag-ui orphan ToolMessages for the
    frontend calls so the LLM gets a complete ToolMessage sequence this turn,
    and ag-ui replaces the orphan messages with real results next turn.
    """
    last = state["messages"][-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return END

    has_backend = any(
        tc.get("name") in PYTHON_TOOL_NAMES
        for tc in last.tool_calls
    )
    return "tools" if has_backend else END


def build_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(AgentState)

    builder.add_node("chat",  chat_node)
    builder.add_node("tools", tools_node)

    builder.set_entry_point("chat")
    builder.add_conditional_edges(
        "chat",
        _should_continue,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "chat")

    # recursion_limit is set via LangGraphAGUIAgent(config=agui_config) in main.py
    return builder.compile(checkpointer=checkpointer)
