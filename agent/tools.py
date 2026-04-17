from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_community.utilities.serpapi import SerpAPIWrapper
from langchain_community.utilities import RequestsWrapper
import os
from typing import List, Optional

# ------------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------------

from pydantic import BaseModel, Field

class PlanTaskInput(BaseModel):
    tasks: List[str] = Field(..., description="List of task descriptions to plan")

class UpdatePlanTaskInput(BaseModel):
    task_id: int = Field(..., description="The 0-based index of the task to update")
    status: str = Field(..., description="New status: 'pending', 'in_progress', or 'done'")

class SearchWebInput(BaseModel):
    query: str = Field(..., description="Search query")
    num_results: int = Field(default=5, description="Number of results to return")

class ScrapeWebsiteInput(BaseModel):
    url: str = Field(..., description="URL to scrape")
    max_chars: int = Field(default=8000, description="Max characters to return from the page")

# ------------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------------

@tool
def plan_tasks(tasks: List[str]) -> str:
    """
    Create a plan with a list of tasks.
    Use this tool at the start of a response to break the work into
    clear steps that will be visible to the user.
    """
    return f"Planned {len(tasks)} tasks: {tasks}"


@tool
def update_plan_task(task_id: int, status: str) -> str:
    """
    Update the status of a plan task.
    Status must be one of: 'pending', 'in_progress', 'done'.
    Use this to keep the user informed of progress.
    """
    valid_statuses = {"pending", "in_progress", "done"}
    if status not in valid_statuses:
        return f"Error: invalid status '{status}'. Must be one of: {valid_statuses}"
    return f"Updated task {task_id} to status '{status}'"


@tool
def search_web(query: str, num_results: int = 5) -> str:
    """
    Search the web using Serp API and return organic search results.
    Use this when you need to find information about a topic or curriculum.
    """
    try:
        api_key = os.getenv("SERPAPI_KEY", "")
        if not api_key:
            return "Search skipped: SERPAPI_KEY not configured"

        serp = SerpAPIWrapper(serpapi_api_key=api_key)
        results = serp.results(query)

        output_parts = []

        # Knowledge panel
        if "knowledge_graph" in results:
            kg = results["knowledge_graph"]
            output_parts.append(
                f"Knowledge Panel: {kg.get('title', '')}\n{kg.get('description', '')}"
            )

        # Organic results
        organic = results.get("organic_results", [])
        for i, r in enumerate(organic[:num_results]):
            output_parts.append(
                f"[{i+1}] {r.get('title', 'No title')}\n"
                f"   URL: {r.get('link', '')}\n"
                f"   {r.get('snippet', '')}"
            )

        return "\n\n".join(output_parts) if output_parts else "No results found"

    except Exception as e:
        return f"Search error: {e}"


@tool
def scrape_website(url: str, max_chars: int = 8000) -> str:
    """
    Scrape the text content of a website URL.
    Use this after search_web to get detailed content from a specific page.
    """
    try:
        wrapper = RequestsWrapper()
        html = wrapper.get(url)

        # Strip HTML tags with a simple regex-based approach
        import re
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[Truncated at {max_chars} chars. Original length: {len(text)}]"

        return f"URL: {url}\n\n{text}"

    except Exception as e:
        return f"Scrape error for {url}: {e}"


# Exported list used by graph.py
PYTHON_TOOLS = [
    plan_tasks,
    update_plan_task,
    search_web,
    scrape_website,
]
