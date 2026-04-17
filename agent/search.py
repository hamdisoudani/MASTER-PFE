from __future__ import annotations
import asyncio
import os
from typing import Any
import httpx

SERPER_API_KEY = os.getenv("SERPERE_API_KEY", "")
SERPER_SEARCH_URL = "https://google.serper.dev/search"
JINA_BASE = "https://r.jina.ai/"


async def serper_search(query: str, num_results: int = 6) -> dict[
    str, Any
]:
    payload: dict[str, Any] = {"q": query, "num": num_results}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                SERPER_SEARCH_URL,
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return {"query": query, "result_urls": [], "error": str(exc)}

    organic = data.get("organic", [])
    return {
        "query": query,
        "result_urls": [r["link"] for r in organic if r.get("link")],
        "snippets": {r["link"]: r.get("snippet", "") for r in organic if r.get("link")},
    }


async def jina_scrape(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            resp = await client.get(
                f"{JINA_BASE}{url}",
                headers={"Accept": "text/plain", "X-Return-Format": "markdown"},
            )
            text = resp.text[:8000]
            lines = text.strip().splitlines()
            title = lines[0].lstrip("# ").strip() if lines else url
            return {"url": url, "title": title, "markdown": text, "success": True}
    except Exception as exc:
        return {"url": url, "title": url, "markdown": "", "success": False, "error": str(exc)}


async def run_search_step(queries: list[str], top_per_query: int = 3) -> list[dict]:
    """
    Run all queries concurrently via Serper. For each query, pick up to top_per_query
    URLs that haven't been selected by a prior query (global dedup).
    Returns a list of SearchQuery dicts ready to store in state.
    """
    raw_results = await asyncio.gather(*[serper_search(q) for q in queries])

    seen_globally: set[str] = set()
    search_data: list[dict] = []

    for r in raw_results:
        selected: list[str] = []
        for url in r.get("result_urls", []):
            if url not in seen_globally and len(selected) < top_per_query:
                selected.append(url)
                seen_globally.add(url)
        search_data.append({
            "query": r["query"],
            "result_urls": r.get("result_urls", []),
            "selected_urls": selected,
        })

    return search_data


async def scrape_selected(search_data: list[dict]) -> list[dict]:
    """Collect all selected_urls across queries, deduplicate, scrape in parallel."""
    seen: set[str] = set()
    urls_to_scrape: list[str] = []
    for sq in search_data:
        for url in sq.get("selected_urls", []):
            if url not in seen:
                urls_to_scrape.append(url)
                seen.ad(url)

    if not urls_to_scrape:
        return []

    results = await asyncio.gather(*[jina_scrape(url) for url in urls_to_scrape])
    return [r for r in results if r.get("success") and r.get("markdown")]
