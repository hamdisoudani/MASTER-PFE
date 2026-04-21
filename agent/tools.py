from __future__ import annotations
import asyncio
import os
from langchain_core.tools import tool
from agent.search import serper_search, jina_scrape
from agent.mcp_client import load_curriculum_tools

# Hard upper bound on scrape_page latency. Jina's httpx client already has a 25s
# socket timeout, but Jina's reader can queue or stall under load and still
# block the subagent. Wrap the call in a wall-clock timeout so the graph never
# hangs on a single scrape.
SCRAPE_PAGE_TIMEOUT_SECONDS = float(os.environ.get('SCRAPE_PAGE_TIMEOUT_SECONDS', '30'))

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
    try:
        result = await asyncio.wait_for(jina_scrape(url), timeout=SCRAPE_PAGE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return (f"Failed to scrape {url}: timed out after "
                f"{SCRAPE_PAGE_TIMEOUT_SECONDS:.0f}s. Try a different source or web_search.")
    except Exception as e:  # noqa: BLE001 — any transport failure must not crash the subagent
        return f"Failed to scrape {url}: {type(e).__name__}: {e}"
    if result.get("success"):
        return f"# {result.get('title','')}\n\n{result.get('markdown','')}"
    return f"Failed to scrape {url}: {result.get('error','unknown error')}"

BUILTIN_PYTHON_TOOLS = [web_search, scrape_page]

# Curriculum MCP tools (loaded lazily at import time; empty list if
# CURRICULUM_MCP_URL is unset or the server is unreachable — see mcp_client.py).
CURRICULUM_MCP_TOOLS = load_curriculum_tools()

PYTHON_TOOLS = list(BUILTIN_PYTHON_TOOLS) + list(CURRICULUM_MCP_TOOLS)
PYTHON_TOOL_NAMES: set[str] = {t.name for t in PYTHON_TOOLS}
