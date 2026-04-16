from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.state import AgentState
from agent.nodes import chat_node, tools_node

# Python-side tool names — only these get routed to tools_node
PYTHON_TOOL_NAMES = {"plan_tasks", "update_plan_task", "search_web", "scrape_website"}


def _should_continue(state: AgentState):
    """
    Route to 'tools' only when the last AIMessage contains at least one
    BACKEND (Python) tool call.  Frontend tool calls (create_syllabus,
    add_chapter, add_lesson, …) must NOT be routed to tools_node — the
    AG-UI framework already emitted them to the frontend via streaming
    and the frontend will execute them.  Sending them to tools_node would
    cause a ToolNode 'tool not found' error and break the flow.
    """
    last = state["messages"][-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return END

    backend_calls = [
        tc for tc in last.tool_calls
        if tc.get("name") in PYTHON_TOOL_NAMES
    ]
    return "tools" if backend_calls else END


def build_graph(checkpointer: BaseCheckpointSaver):
    """Compile the agent graph with the supplied checkpointer."""
    builder = StateGraph(AgentState)
    builder.add_node("chat", chat_node)
    builder.add_node("tools", tools_node)
    builder.set_entry_point("chat")
    builder.add_conditional_edges(
        "chat", _should_continue, {"tools": "tools", END: END}
    )
    builder.add_edge("tools", "chat")
    compiled = builder.compile(checkpointer=checkpointer)
    return compiled.with_config({"recursion_limit": 150})
