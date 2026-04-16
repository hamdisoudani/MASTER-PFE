"""Agent state — extends CopilotKitState with UI-renderable fields."""
from typing import Optional
from copilotkit import CopilotKitState


class AgentState(CopilotKitState):
    """
    plan            → list of {id, task, status} set by plan_tasks tool
    search_results  → {query, results:[{title,url,snippet}]} set by search_web
    scraped_content → {url, title, content} set by scrape_website
    current_activity→ human-readable string of what the agent is doing
    finished        → True once the agent is done with a task
    """
    plan: Optional[list] = None
    search_results: Optional[dict] = None
    scraped_content: Optional[dict] = None
    current_activity: Optional[str] = None
    finished: bool = False
