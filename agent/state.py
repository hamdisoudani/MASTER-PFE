from __future__ import annotations
from typing import Optional, Literal
from typing_extensions import TypedDict
from copilotkit import CopilotKitState


class SearchQuery(TypedDict):
    query: str
    result_urls: list[str]    # all URLs from Serper organic results
    selected_urls: list[str]  # top URLs chosen for scraping (filled by scraper_node)


class PlanStep(TypedDict):
    id: int
    type: Literal["task", "search"]
    title: str
    status: Literal["pending", "in_progress", "done"]
    queries: Optional[list[str]]               # search steps only — set at plan creation
    search_data: Optional[list[SearchQuery]]   # filled by search_subgraph after running


class ScrapedPage(TypedDict):
    url: str
    title: str
    markdown: str


class AgentState(CopilotKitState):
    plan: list[PlanStep]
    scraped_pages: list[ScrapedPage]
    current_activity: Optional[str]
    finished: bool
