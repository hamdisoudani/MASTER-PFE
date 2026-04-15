"""LangGraph graph definition."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .state import AgentState
from .nodes import chat_node, planner_node


def _route(state: AgentState) -> str:
    """Route to planner if the user is asking for a plan, else chat."""
    last_human = next(
        (
            m
            for m in reversed(state.get("messages", []))
            if hasattr(m, "type") and m.type == "human"
        ),
        None,
    )
    if last_human is not None:
        content = str(last_human.content).lower()
        if any(k in content for k in ("plan", "steps", "roadmap", "outline")):
            return "planner"
    return "chat"


def build_graph():
    """Build and compile the LangGraph state machine."""
    builder: StateGraph = StateGraph(AgentState)

    builder.add_node("chat", chat_node)
    builder.add_node("planner", planner_node)

    builder.set_conditional_entry_point(
        _route,
        {"chat": "chat", "planner": "planner"},
    )

    builder.add_edge("chat", END)
    builder.add_edge("planner", END)

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


# Singleton compiled graph
graph = build_graph()
