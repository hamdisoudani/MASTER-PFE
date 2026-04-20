"""Curriculum MCP client wiring for the syllabus agent.

PR3 (feat/supabase-mcp-curriculum): load the tools exposed by
`curriculum-mcp` (FastMCP, streamable-http) into the agent at graph build time,
so the LLM can call `addChapter`, `addLesson`, `updateLessonContent`,
`appendLessonContent`, `patchLessonBlocks`, `readLessonBlocks`,
`getSyllabusOutline`, etc. directly — server-side, bypassing the
`interrupt()` confirmation path used for other frontend tools.

Environment:
- `CURRICULUM_MCP_URL`  — e.g. `http://localhost:8080/mcp` (required to enable)
- `CURRICULUM_MCP_TOKEN` — optional bearer token

If `CURRICULUM_MCP_URL` is unset OR the MCP server is unreachable at build time,
`load_curriculum_tools()` returns `[]` and the agent falls back to the
pre-MCP behavior (frontend-shell mutations through `interrupt()`). This keeps
the branch usable in `main`-equivalent mode while the Supabase path is still
being wired end-to-end.
"""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

CURRICULUM_TOOL_NAMES = {
    "getOrCreateSyllabus",
    "getSyllabusOutline",
    "listChapters",
    "addChapter",
    "listLessons",
    "readLessonBlocks",
    "addLesson",
    "updateLessonContent",
    "appendLessonContent",
    "patchLessonBlocks",
}


async def _aload_curriculum_tools() -> list[Any]:
    url = os.environ.get("CURRICULUM_MCP_URL", "").strip()
    if not url:
        logger.info("CURRICULUM_MCP_URL unset; skipping curriculum-mcp tool load")
        return []
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except Exception as e:  # noqa: BLE001
        logger.warning("langchain-mcp-adapters not installed: %s", e)
        return []

    headers: dict[str, str] = {}
    token = os.environ.get("CURRICULUM_MCP_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    server_cfg: dict[str, Any] = {
        "curriculum": {
            "transport": "streamable_http",
            "url": url,
        }
    }
    if headers:
        server_cfg["curriculum"]["headers"] = headers

    try:
        client = MultiServerMCPClient(server_cfg)
        tools = await client.get_tools()
    except Exception as e:  # noqa: BLE001
        logger.warning("failed to load curriculum-mcp tools from %s: %s", url, e)
        return []

    loaded = [t for t in tools if getattr(t, "name", None) in CURRICULUM_TOOL_NAMES]
    logger.info("curriculum-mcp loaded %d tools: %s", len(loaded), [t.name for t in loaded])
    return loaded


def load_curriculum_tools() -> list[Any]:
    """Sync wrapper for graph build. Safe to call from module import."""
    try:
        return asyncio.run(_aload_curriculum_tools())
    except RuntimeError:
        # already inside an event loop (e.g. langgraph dev hot-reload)
        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_aload_curriculum_tools())
            finally:
                loop.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("curriculum-mcp load fallback failed: %s", e)
            return []
