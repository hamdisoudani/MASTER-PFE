"""Tests for the persistent checkpoint garbage collector.

Covers agent.middleware.gc_persistent_messages — which must:
  * return replacement messages with the SAME message id as the original
    (so the add_messages reducer rewrites in place),
  * strip heavy content/blocks arrays out of older lesson-mutation
    tool_call args, preserving tool_call_id,
  * truncate bulky older read-tool results (scrape_page, web_search, ...)
    while preserving tool_call_id and message id,
  * leave messages inside the KEEP_RECENT_TURNS window UNTOUCHED,
  * never create orphan tool_call ↔ ToolMessage pairs,
  * return [] when nothing qualifies for GC.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.middleware import (
    KEEP_RECENT_TURNS,
    MAX_TOOL_RESULT_CHARS,
    gc_persistent_messages,
)


def _mk_mutation_turn(i: int, block_count: int = 12) -> list:
    ai = AIMessage(
        content="",
        id=f"ai-{i}",
        tool_calls=[{
            "id": f"tc-{i}",
            "name": "addLesson",
            "args": {
                "chapterId": f"ch-{i}",
                "title": f"Lesson {i}",
                "content": [{"type": "p", "text": "x" * 500} for _ in range(block_count)],
            },
        }],
    )
    tm = ToolMessage(content="ok", tool_call_id=f"tc-{i}", id=f"tm-{i}")
    return [HumanMessage(content=f"write lesson {i}", id=f"h-{i}"), ai, tm]


def _mk_scrape_turn(i: int, size: int = 10000) -> list:
    ai = AIMessage(
        content="",
        id=f"ai-s-{i}",
        tool_calls=[{"id": f"tc-s-{i}", "name": "scrape_page", "args": {"url": f"https://x/{i}"}}],
    )
    tm = ToolMessage(content="Z" * size, tool_call_id=f"tc-s-{i}", id=f"tm-s-{i}")
    return [HumanMessage(content=f"research {i}", id=f"h-s-{i}"), ai, tm]


def test_gc_empty_and_small_returns_nothing():
    assert gc_persistent_messages([]) == []
    msgs = []
    for i in range(KEEP_RECENT_TURNS):
        msgs.extend(_mk_mutation_turn(i))
    assert gc_persistent_messages(msgs) == []


def test_gc_elides_old_mutation_blocks_preserves_ids():
    msgs = []
    for i in range(KEEP_RECENT_TURNS + 3):
        msgs.extend(_mk_mutation_turn(i))
    updates = gc_persistent_messages(msgs)
    assert updates, "expected rewrites for older mutation turns"
    # Every returned AIMessage must preserve id and have elided content.
    ai_updates = [u for u in updates if isinstance(u, AIMessage)]
    assert ai_updates
    for u in ai_updates:
        assert u.id and u.id.startswith("ai-")
        assert len(u.tool_calls) == 1
        elided = u.tool_calls[0]["args"]["content"]
        assert elided == [{"__elided__": True, "blockCount": 12}]
        assert u.tool_calls[0]["id"].startswith("tc-")  # tool_call_id preserved


def test_gc_leaves_recent_window_untouched():
    msgs = []
    for i in range(KEEP_RECENT_TURNS + 3):
        msgs.extend(_mk_mutation_turn(i))
    updates = gc_persistent_messages(msgs)
    touched_ids = {u.id for u in updates}
    # Indices 3..(N-1) are in the recent window; their ids must NOT be in updates.
    recent_ai_ids = {f"ai-{i}" for i in range(3, KEEP_RECENT_TURNS + 3)}
    assert not (touched_ids & recent_ai_ids), (
        f"recent window must not be GC'd: leaked {touched_ids & recent_ai_ids}"
    )


def test_gc_truncates_old_scrape_results_preserving_ids():
    msgs = []
    for i in range(KEEP_RECENT_TURNS + 2):
        msgs.extend(_mk_scrape_turn(i, size=MAX_TOOL_RESULT_CHARS * 4))
    updates = gc_persistent_messages(msgs)
    tm_updates = [u for u in updates if isinstance(u, ToolMessage)]
    assert tm_updates, "expected scrape ToolMessages to be trimmed"
    for u in tm_updates:
        assert u.id and u.id.startswith("tm-s-")
        assert u.tool_call_id.startswith("tc-s-")
        assert len(u.content) < MAX_TOOL_RESULT_CHARS
        assert "elided" in u.content


def test_gc_preserves_tool_call_bonds():
    msgs = []
    for i in range(KEEP_RECENT_TURNS + 4):
        msgs.extend(_mk_mutation_turn(i))
        msgs.extend(_mk_scrape_turn(i))
    updates = gc_persistent_messages(msgs)
    # Simulate reducer replacement by id.
    by_id = {m.id: m for m in msgs if getattr(m, "id", None)}
    for u in updates:
        by_id[u.id] = u
    merged = list(by_id.values())
    open_ids = set()
    for m in merged:
        if isinstance(m, AIMessage):
            for tc in (m.tool_calls or []):
                open_ids.add(tc["id"])
        elif isinstance(m, ToolMessage):
            open_ids.discard(m.tool_call_id)
    assert not open_ids, f"orphan tool_calls after GC: {open_ids}"


def test_gc_skips_messages_without_ids():
    ai_no_id = AIMessage(
        content="",
        tool_calls=[{"id": "tcX", "name": "addLesson",
                     "args": {"content": [{"t": "x"} for _ in range(5)]}}],
    )
    tm_no_id = ToolMessage(content="ok", tool_call_id="tcX")
    msgs = [HumanMessage(content="q0", id="h0"), ai_no_id, tm_no_id]
    for i in range(KEEP_RECENT_TURNS + 1):
        msgs.extend(_mk_mutation_turn(100 + i))
    updates = gc_persistent_messages(msgs)
    # None of the updates should correspond to the id-less older AIMessage,
    # because we can't safely replace without an id.
    assert all(getattr(u, "id", None) for u in updates)
