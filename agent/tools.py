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
async def submit_plan(steps: list[dict]) -> str:
    """Register the authoring plan for the current thread.

    Call this ONCE after the user has confirmed what they want, before
    writing any lesson. `steps` is the ordered list of lessons you will
    author, each step a dict:
      - chapter_title: str (required) — the chapter this lesson lives in
      - lesson_title : str (required) — the title of the lesson itself
      - brief        : str (optional) — 1-2 sentence description of what
                       this lesson must cover, used as the writer's brief

    The graph persists the plan to agent state and routes the writer
    through each step in order. You do NOT decide when to move on — the
    graph advances the cursor automatically after the critic passes a
    lesson. To change the plan mid-run, call submit_plan again with the
    full updated list. Returns a confirmation with the normalized plan.
    """
    normalized = []
    for i, step in enumerate(steps or []):
        if not isinstance(step, dict):
            continue
        normalized.append({
            "chapter_title": str(step.get("chapter_title") or "").strip(),
            "lesson_title": str(step.get("lesson_title") or "").strip(),
            "brief": str(step.get("brief") or "").strip(),
            "status": "pending",
            "attempts": 0,
            "draft_lesson_id": None,
        })
    # A marker the tools_post_hook recognizes to flip state. Returning the
    # JSON envelope here lets the model see the plan echoed back.
    import json as _json
    return _json.dumps({"ok": True, "step_count": len(normalized),
                        "plan": normalized,
                        "_submit_plan_marker": True})


BUILTIN_PYTHON_TOOLS = [web_search, scrape_page, submit_plan]

# The "normal" (classic) syllabus agent writes to the IN-MEMORY DRAFT store.
# Persistent Supabase-backed mutations are reserved for the writer / summarizer
# subagents in the deep graph (see agent/deep_graph.py).
CURRICULUM_MCP_TOOLS = load_curriculum_tools(mode="draft")

PYTHON_TOOLS = list(BUILTIN_PYTHON_TOOLS) + list(CURRICULUM_MCP_TOOLS)
PYTHON_TOOL_NAMES: set[str] = {t.name for t in PYTHON_TOOLS}
