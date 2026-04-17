"""Tool definitions and async executor functions for the Syllabus AI agent.

Exports used by nodes.py:
    PYTHON_TOOLS          - list of @tool objects bound to the LLM
    PYTHON_TOOL_NAMES     - set of tool name strings (used for routing)
    _exec_plan_tasks      - async executor
    _exec_update_plan_task - async executor
    _exec_search_web      - async executor
    _exec_scrape_website  - async executor
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# @tool objects – bound to the LLM so it knows the schema
# ---------------------------------------------------------------------------

@tool
def plan_tasks(tasks: list[str]) -> str:
    """Create a visible step-by-step plan. Call this FIRST for any multi-step request."""
    return json.dumps({"planned": tasks})


@tool
def update_plan_task(task_id: int, status: str) -> str:
    """Update a plan task status. status must be: pending | in_progress | done."""
    return json.dumps({"updated": task_id, "status": status})


@tool
def search_web(query: str, country: str = "us", time_period: str = "", num_results: int = 6) -> str:
    """Search the web via Serper API and return organic results."""
    return json.dumps({"query": query})


@tool
def scrape_website(url: str) -> str:
    """Fetch and return the readable text content of a web page."""
    return json.dumps({"url": url})


# Exported for LLM binding
PYTHON_TOOLS: list = [plan_tasks, update_plan_task, search_web, scrape_website]

# Exported for routing in graph.py / nodes.py
PYTHON_TOOL_NAMES: set[str] = {t.name for t in PYTHON_TOOLS}


# ---------------------------------------------------------------------------
# Async executor functions – called by python_tools_node in nodes.py
# Each returns (content_str, state_updates_dict)
# ---------------------------------------------------------------------------

async def _exec_plan_tasks(tasks: list[str]) -> tuple[str, dict]:
    """Build the initial plan and store it in agent state."""
    plan = [
        {"id": i, "description": desc, "status": "pending"}
        for i, desc in enumerate(tasks)
    ]
    content = json.dumps({"ok": True, "planned": len(plan), "tasks": plan})
    return content, {"plan": plan}


async def _exec_update_plan_task(
    task_id: int,
    status: str,
    current_plan: list[dict],
) -> tuple[str, dict]:
    """Mutate the status of one task in the plan."""
    valid = {"pending", "in_progress", "done"}
    if status not in valid:
        return json.dumps({"error": f"Invalid status '{status}'. Must be one of {valid}"}), {}

    updated_plan = [
        {**task, "status": status} if task.get("id") == task_id else task
        for task in (current_plan or [])
    ]
    content = json.dumps({"ok": True, "task_id": task_id, "new_status": status})
    return content, {"plan": updated_plan}


async def _exec_search_web(
    query: str,
    country: str = "us",
    time_period: str = "",
    num_results: int = 6,
) -> tuple[str, dict]:
    """Search via Serper API (https://serper.dev). Falls back gracefully if key absent."""
    api_key = os.getenv("SERPER_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "SERPER_API_KEY not configured"}), {}

    payload: dict[str, Any] = {"q": query, "num": num_results, "gl": country}
    if time_period:
        payload["tbs"] = time_period

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return json.dumps({"error": str(exc)}), {}

    parts: list[str] = []

    kg = data.get("knowledgeGraph", {})
    if kg:
        parts.append(f"Knowledge panel: {kg.get('title', '')} — {kg.get('description', '')}")

    for i, r in enumerate(data.get("organic", [])[:num_results]):
        parts.append(
            f"[{i + 1}] {r.get('title', '')}\n"
            f"    URL: {r.get('link', '')}\n"
            f"    {r.get('snippet', '')}"
        )

    content = "\n\n".join(parts) if parts else "No results found."
    return content, {}


async def _exec_scrape_website(url: str) -> tuple[str, dict]:
    """Fetch a URL and return stripped plain text (max 8 000 chars)."""
    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SyllabusBot/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        return json.dumps({"error": str(exc)}), {}

    # Strip scripts, styles, then tags
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    MAX = 8_000
    if len(text) > MAX:
        text = text[:MAX] + f"\n\n[Truncated — original length {len(text)} chars]"

    return f"URL: {url}\n\n{text}", {}
