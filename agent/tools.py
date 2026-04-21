from __future__ import annotations
from langchain_core.tools import tool
from agent.search import serper_search, jina_scrape
from agent.mcp_client import load_curriculum_tools

@tool
async def web_search(query: str) -> str:
    """Search the web for up-to-date information. Returns top result URLs with snippets."""
    result = await serper_search(query)
    urls = result.get("result_urls", []) or []
    snippets = result.get("snippets", {}) or {}
    lines = []
    for url in urls[:6]:
        snippet = snippets.get(url, "")
        lines.append(f"- {url}\n  {snippet}")
    return "\n".join(lines) if lines else "No results found."

@tool
async def scrape_page(url: str) -> str:
    """Fetch a web page and return its readable content as markdown."""
    result = await jina_scrape(url)
    if result.get("success"):
        return f"# {result.get('title','')}\n\n{result.get('markdown','')}"
    return f"Failed to scrape {url}: {result.get('error','unknown error')}"

@tool
async def submit_plan(chapters: list[dict]) -> str:
    """Register the hierarchical authoring plan.

    Call this ONCE, after you have agreed with the user on scope and before
    authoring anything. The graph then drives the agent chapter-by-chapter,
    lesson-by-lesson, advancing the cursor deterministically.

    Args:
        chapters: ordered list. Each item:
            {
              "title":   str   # chapter title
              "summary": str   # 1-2 sentence chapter summary
              "lessons": [
                  {"title": str, "brief": str},  # brief = 1-2 sentence scope
                  ...
              ],
            }

    Returns:
        Human-readable confirmation. The actual plan lives in agent state
        (see tools_post_hook), so subsequent nodes can advance the cursor
        without re-parsing the tool call.
    """
    total_chapters = len(chapters or [])
    total_lessons = sum(len((c or {}).get("lessons") or []) for c in (chapters or []))
    return (
        f"Plan registered: {total_chapters} chapters, {total_lessons} lessons. "
        "The graph will advance you through them one at a time — do not pick the "
        "next step yourself, follow the SystemMessage you receive after each pass."
    )


BUILTIN_PYTHON_TOOLS = [web_search, scrape_page, submit_plan]

# The "normal" (classic) syllabus agent writes to the IN-MEMORY DRAFT store.
# Persistent Supabase-backed mutations are reserved for the writer / summarizer
# subagents in the deep graph (see agent/deep_graph.py).
# v2: syllabus_agent now writes to Supabase directly via persistent tools.
# The old draft-store path is still available to subagents (deep_graph) via
# load_curriculum_tools(mode="draft") elsewhere, but the classic agent has no
# business holding data in a volatile in-memory bucket.
CURRICULUM_MCP_TOOLS = load_curriculum_tools(mode="persistent")

PYTHON_TOOLS = list(BUILTIN_PYTHON_TOOLS) + list(CURRICULUM_MCP_TOOLS)
PYTHON_TOOL_NAMES: set[str] = {t.name for t in PYTHON_TOOLS}
