"""
Python-side agent tools: plan_tasks, search_web, scrape_website
These are bound to the LLM in nodes.py alongside the frontend (CopilotKit) tools.
"""
import os
import json
import httpx
from langchain_core.tools import tool

SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_SCRAPE_URL = "https://scrape.serper.dev"


def _headers() -> dict:
    return {
        "X-API-KEY": os.getenv("SERPER_API_KEY", ""),
        "Content-Type": "application/json",
    }


@tool
def plan_tasks(tasks: list) -> str:
    """
    Create a step-by-step plan before building a syllabus.
    ALWAYS call this first for any request involving 2+ chapters.
    tasks: list of concrete steps, e.g.:
      ["Search for Python basics vocabulary",
       "Create syllabus",
       "Add chapter: Introduction",
       "Add lesson: What is Python",
       ...]
    Returns the plan as a JSON array so the frontend can render it.
    """
    plan = [{"id": i, "task": t, "status": "pending"} for i, t in enumerate(tasks)]
    return json.dumps(plan)


@tool
def search_web(
    query: str,
    country: str = "us",
    time_period: str = "",
    num_results: int = 6,
) -> str:
    """
    Search the web using Serper API. Use this BEFORE writing any lesson to:
    - Verify correct terminology and vocabulary for the subject
    - Find standard curriculum structures for the field
    - Get definitions, key concepts, and real-world examples
    - Research best practices and current standards

    country: ISO 2-letter country code (us, fr, gb, de, jp, ma, ...)
    time_period: '' (any time), 'd' (past day), 'w' (past week), 'm' (past month), 'y' (past year)
    num_results: number of results to return (1-10)
    """
    payload: dict = {
        "q": query,
        "gl": country,
        "num": min(max(num_results, 1), 10),
        "hl": "en",
    }
    if time_period:
        payload["tbs"] = f"qdr:{time_period}"

    try:
        r = httpx.post(SERPER_SEARCH_URL, json=payload, headers=_headers(), timeout=15)
        data = r.json()

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "position": item.get("position", 0),
            }
            for item in data.get("organic", [])
        ]

        knowledge = data.get("knowledgeGraph", {})
        output: dict = {
            "query": query,
            "country": country,
            "total": len(results),
            "results": results,
        }
        if knowledge:
            output["knowledge_panel"] = {
                "title": knowledge.get("title", ""),
                "description": knowledge.get("description", ""),
                "attributes": knowledge.get("attributes", {}),
            }
        return json.dumps(output)
    except Exception as exc:
        return json.dumps({"error": str(exc), "query": query, "results": []})


@tool
def scrape_website(url: str) -> str:
    """
    Scrape a specific webpage and return its full content as structured markdown.
    Use this when a search result looks authoritative and you want the complete content.
    Best targets: Wikipedia articles, educational platforms, documentation pages,
    official curriculum guides.
    The returned markdown can be used directly to write accurate lesson content.
    """
    try:
        r = httpx.post(
            SERPER_SCRAPE_URL,
            json={"url": url, "includeMarkdown": True},
            headers=_headers(),
            timeout=20,
        )
        data = r.json()
        content = data.get("markdown") or data.get("text") or ""
        if len(content) > 8000:
            content = content[:8000] + "\n\n[... content truncated for length ...]"
        return json.dumps({
            "url": url,
            "title": data.get("title", url),
            "content": content,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc), "url": url, "content": ""})


PYTHON_TOOLS = [plan_tasks, search_web, scrape_website]
