"""Tool definitions + async executors aligned with AgentState."""
from __future__ import annotations
import json
from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults

_tavily = TavilySearchResults(max_results=4)


@tool
def set_plan(tasks: list[dict]) -> str:
    """Set the agent execution plan. tasks is a list of {id, task, status} dicts."""
    return json.dumps(tasks)


@tool
def update_activity(activity: str) -> str:
    """Update the current activity description shown to the user."""
    return activity


@tool
def search_web(query: str) -> str:
    """Search the web for educational content about a topic."""
    return ""


@tool
def mark_finished(finished: bool = True) -> str:
    """Mark the agent task as finished."""
    return str(finished)


def get_tools():
    return [set_plan, update_activity, search_web, mark_finished]


async def execute_tool(name: str, args: dict, config: dict) -> dict:
    """Execute a tool by name and return a state-patch dict."""
    if name == "set_plan":
        return {"plan": args.get("tasks", [])}

    if name == "update_activity":
        return {"current_activity": args.get("activity", "")}

    if name == "mark_finished":
        return {"finished": args.get("finished", True)}

    if name == "search_web":
        results = await _tavily.ainvoke(args["query"])
        return {
            "search_results": {"query": args["query"], "results": results},
            "current_activity": f"Searched: {args['query']}",
        }

    return {}
