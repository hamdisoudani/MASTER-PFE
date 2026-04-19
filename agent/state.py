from __future__ import annotations
from typing import Annotated, Optional, Literal, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class SearchQuery(TypedDict):
    query: str
    result_urls: list[str]
    selected_urls: list[str]


class PlanStep(TypedDict):
    id: int
    type: Literal["task", "search"]
    title: str
    status: Literal["pending", "in_progress", "searching", "done"]
    queries: Optional[list[str]]
    search_data: Optional[list[SearchQuery]]


class ScrapedPage(TypedDict):
    url: str
    title: str
    markdown: str


class AgentState(TypedDict, total=False):
    """Pure-LangGraph agent state.

    Frontend tool schemas are passed via `config["configurable"]["frontend_tools"]`
    (a list of JSON-schema-ish tool dicts) — NOT via state anymore. The LLM sees
    them alongside the Python tools.  When the LLM emits a tool_call for a
    frontend tool, we:
      1. stop the graph (end) so the stream delivers the AIMessage to the client
      2. emit a compressed Pusher notification on channel `thread-<thread_id>`
    The client executes the tool and resumes the run by submitting a ToolMessage
    (via `useStream.submit({messages:[ToolMessage(...)]})`).
    """

    messages: Annotated[list, add_messages]
    plan: list[PlanStep]
    currentStepIndex: int
    planStatus: Literal["idle", "in_progress", "done"]
    search_results: list[SearchQuery]
    scraped_pages: list[ScrapedPage]
    current_activity: Optional[str]
    finished: bool
    editor_context: Optional[dict[str, Any]]
