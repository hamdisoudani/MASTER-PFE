"""State garbage collector for heavy per-turn tool payloads.

The agent accumulates three classes of bulky state between turns:

1. ``research_cache`` — scraped markdown mirrored from ``scrape_page``
   so the writer can cite without rehydrating chat history. Grows
   unboundedly as the user browses.
2. ``lesson_blocks_cache`` — full block arrays aggregated across
   ``addLesson`` + ``appendLessonContent`` batches. Once the critic
   accepts a lesson we never need the blocks in state again.
3. ``critic_reports`` — per-lesson rubric verdicts. Only the latest
   failing one is useful; passed lessons can be dropped.

This module provides ``gc_state(state)`` which returns a partial state
update that trims all three. It is called from ``chat_node`` at the top
of every turn so persistence (LangGraph checkpointer) stores a small
delta, and so the next turn reads a lean state.

Design constraints:
- Pure function of ``state`` → partial dict. Safe to merge.
- Never drops an ACTIVE record (currently-failing lesson, unread
  critic feedback). Only prunes what's already consumed or stale.
- Deterministic — no I/O, no LLM calls, no randomness.
"""
from __future__ import annotations
import os
from typing import Any

# Tunables (env-overridable so ops can dial them without redeploy).
MAX_RESEARCH_ENTRIES_PER_BUCKET = int(os.getenv("AGENT_GC_MAX_RESEARCH_PER_BUCKET", "8"))
MAX_RESEARCH_BUCKETS = int(os.getenv("AGENT_GC_MAX_RESEARCH_BUCKETS", "24"))
MAX_RESEARCH_MARKDOWN_CHARS = int(os.getenv("AGENT_GC_MAX_RESEARCH_CHARS", "2000"))
MAX_BLOCKS_CACHE_LESSONS = int(os.getenv("AGENT_GC_MAX_BLOCKS_CACHE", "12"))
MAX_CRITIC_REPORTS = int(os.getenv("AGENT_GC_MAX_CRITIC_REPORTS", "24"))


def _gc_research_cache(cache: dict[str, list[dict[str, Any]]] | None) -> tuple[dict[str, list[dict[str, Any]]], int]:
    if not cache:
        return {}, 0
    dropped = 0
    out: dict[str, list[dict[str, Any]]] = {}
    # 1) keep only the N most recent buckets (dict iteration order == insertion order in CPython 3.7+)
    buckets = list(cache.items())
    if len(buckets) > MAX_RESEARCH_BUCKETS:
        dropped += sum(len(v) for _, v in buckets[: len(buckets) - MAX_RESEARCH_BUCKETS])
        buckets = buckets[-MAX_RESEARCH_BUCKETS :]
    # 2) inside each bucket, keep the last K entries and truncate markdown
    for key, entries in buckets:
        trimmed = entries[-MAX_RESEARCH_ENTRIES_PER_BUCKET:]
        dropped += max(0, len(entries) - len(trimmed))
        out[key] = [
            {**e, "markdown": (e.get("markdown") or "")[:MAX_RESEARCH_MARKDOWN_CHARS]}
            for e in trimmed
        ]
    return out, dropped


def _gc_lesson_blocks_cache(
    cache: dict[str, list[dict[str, Any]]] | None,
    reports: dict[str, dict[str, Any]] | None,
    last_authored: dict[str, Any] | None,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    if not cache:
        return {}, 0
    reports = reports or {}
    active_lesson = (last_authored or {}).get("lesson_id")
    kept: dict[str, list[dict[str, Any]]] = {}
    dropped = 0
    for lesson_id, blocks in cache.items():
        report = reports.get(lesson_id) or {}
        accepted = bool(report.get("pass"))
        is_active = lesson_id == active_lesson
        if accepted and not is_active:
            dropped += 1
            continue
        kept[lesson_id] = blocks
    # Hard cap — if critic never ran on older lessons, keep the most recent
    if len(kept) > MAX_BLOCKS_CACHE_LESSONS:
        items = list(kept.items())
        dropped += len(items) - MAX_BLOCKS_CACHE_LESSONS
        kept = dict(items[-MAX_BLOCKS_CACHE_LESSONS:])
    return kept, dropped


def _gc_critic_reports(
    reports: dict[str, dict[str, Any]] | None,
    attempts: dict[str, int] | None,
) -> tuple[dict[str, dict[str, Any]], int]:
    if not reports:
        return {}, 0
    attempts = attempts or {}
    # Keep every currently-failing lesson + the latest N passed ones.
    failing = {k: v for k, v in reports.items() if not v.get("pass")}
    passed = [(k, v) for k, v in reports.items() if v.get("pass")]
    keep_passed = passed[-MAX_CRITIC_REPORTS:]
    dropped = len(passed) - len(keep_passed)
    merged = {**dict(keep_passed), **failing}
    # Also drop attempt counters for accepted lessons.
    return merged, dropped


def gc_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return a partial state dict pruning heavy entries.

    Merges cleanly via LangGraph's dict update semantics. Safe to call
    even when the relevant keys are missing.
    """
    research, r_dropped = _gc_research_cache(state.get("research_cache"))
    reports, c_dropped = _gc_critic_reports(state.get("critic_reports"), state.get("revision_attempts"))
    blocks, b_dropped = _gc_lesson_blocks_cache(
        state.get("lesson_blocks_cache"),
        reports,
        state.get("last_authored_lesson"),
    )
    # Only emit keys that actually changed — keeps the checkpoint delta small.
    out: dict[str, Any] = {}
    if research != (state.get("research_cache") or {}):
        out["research_cache"] = research
    if reports != (state.get("critic_reports") or {}):
        out["critic_reports"] = reports
    if blocks != (state.get("lesson_blocks_cache") or {}):
        out["lesson_blocks_cache"] = blocks
    # Prune revision_attempts for lessons that were accepted.
    attempts = state.get("revision_attempts") or {}
    if attempts:
        cleaned = {k: v for k, v in attempts.items() if k in blocks}
        if cleaned != attempts:
            out["revision_attempts"] = cleaned
    if r_dropped or c_dropped or b_dropped:
        out["gc_stats"] = {
            "research_entries_dropped": r_dropped,
            "critic_reports_dropped": c_dropped,
            "lesson_blocks_dropped": b_dropped,
        }
    return out
