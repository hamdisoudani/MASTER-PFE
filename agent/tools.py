"""Tool definitions (schemas) + async executors."""
from __future__ import annotations
import json
from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from agent.syllabus_manager import SyllabusManager


# ── Schema tools (used for bind_tools) ──────────────────────────────────────

@tool
def create_syllabus(title: str, description: str = "") -> str:
    """Create a new syllabus with the given title and optional description."""
    return ""


@tool
def add_chapter(syllabus_id: str, title: str, order: int = 0) -> str:
    """Add a chapter to a syllabus."""
    return ""


@tool
def add_lesson(chapter_id: str, title: str, content: str = "", order: int = 0) -> str:
    """Add a lesson to a chapter."""
    return ""


@tool
def update_lesson_content(lesson_id: str, content: str) -> str:
    """Update the markdown content of a lesson."""
    return ""


@tool
def delete_item(item_id: str, item_type: str) -> str:
    """Delete a syllabus, chapter, or lesson by id. item_type: syllabus|chapter|lesson"""
    return ""


@tool
def search_web(query: str) -> str:
    """Search the web for educational content about a topic."""
    return ""


def get_tools():
    return [create_syllabus, add_chapter, add_lesson, update_lesson_content, delete_item, search_web]


# ── Async executors ──────────────────────────────────────────────────────────

_tavily = TavilySearchResults(max_results=4)


async def execute_tool(name: str, args: dict, config: dict) -> str:
    mgr: SyllabusManager = config["configurable"]["syllabus_manager"]

    if name == "create_syllabus":
        obj = await mgr.create_syllabus(args["title"], args.get("description", ""))
        return json.dumps(obj)

    if name == "add_chapter":
        obj = await mgr.add_chapter(args["syllabus_id"], args["title"], args.get("order", 0))
        return json.dumps(obj)

    if name == "add_lesson":
        obj = await mgr.add_lesson(
            args["chapter_id"], args["title"],
            args.get("content", ""), args.get("order", 0)
        )
        return json.dumps(obj)

    if name == "update_lesson_content":
        obj = await mgr.update_lesson(args["lesson_id"], args["content"])
        return json.dumps(obj)

    if name == "delete_item":
        obj = await mgr.delete_item(args["item_id"], args["item_type"])
        return json.dumps(obj)

    if name == "search_web":
        results = await _tavily.ainvoke(args["query"])
        return json.dumps(results)

    return f"Unknown tool: {name}"
