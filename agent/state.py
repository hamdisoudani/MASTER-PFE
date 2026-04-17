from __future__ import annotations
from typing import Optional, Literal
from typing_extensions import TypedDict
from copilotkit import CopilotKitState


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


class AgentState(CopilotKitState):
    plan: list[PlanStep]
    currentStepIndex: int
    planStatus: Literal["idle", "in_progress", "done"]
    search_results: list[SearchQuery]
    scraped_pages: list[ScrapedPage]
    current_activity: Optional[str]
    finished: bool
