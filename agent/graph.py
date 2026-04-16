"""LangGraph state machine for Syllabus AI."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .nodes import chat_node

_builder = StateGraph(AgentState)
_builder.add_node("chat", chat_node)
_builder.set_entry_point("chat")
_builder.add_edge("chat", END)

memory = MemorySaver()
graph = _builder.compile(checkpointer=memory)
