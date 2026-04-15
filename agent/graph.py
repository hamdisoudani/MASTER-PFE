"""LangGraph state machine for the Master PFE agent."""
from __future__ import annotations

from typing import Any, List, Optional

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import Annotated, TypedDict

from .llm import get_llm

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    tools: List[Any]
    copilotkit: Optional[dict]

async def chat_node(state: AgentState) -> dict:
    """Call the LLM and return its reply."""
    llm = get_llm()
    system = SystemMessage(
        content=(
            "You are a helpful AI assistant. "
            "Answer concisely and clearly. "
            "If you don't know something, say so."
        )
    )
    messages = [system] + list(state["messages"])
    response = await llm.ainvoke(messages)
    return {"messages": [response]}

def _route(state: AgentState) -> str:
    return "chat"

_builder = StateGraph(AgentState)
_builder.add_node("chat", chat_node)
_builder.set_conditional_entry_point(_route)
_builder.add_edge("chat", END)

memory = MemorySaver()
graph = _builder.compile(checkpointer=memory)
