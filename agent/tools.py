from __future__ import annotations
from langchain_core.tools import tool
from agent.search import serper_search, jina_scrape


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


PYTHON_TOOLS = [web_search, scrape_page]
PYTHON_TOOL_NAMES: set[str] = {t.name for t in PYTHON_TOOLS}
