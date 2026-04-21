"""Draft-mode MCP tools. Mirror the real curriculum tools, but write
to an in-memory draft store instead of Supabase. Used by the "normal
syllabus agent" and the deep-agent supervisor so drafting iterations
don't hit the database. Writer / summarizer subagents still use the
real persistent tools registered in `tools.py`.
"""
from __future__ import annotations
from typing import Optional
from mcp.server.fastmcp import FastMCP

from . import draft_store


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def draftGetOrCreateSyllabus(thread_id: str, title: Optional[str] = None) -> dict:
        """Return the IN-MEMORY DRAFT syllabus for a thread, creating it if missing."""
        return draft_store.get_or_create_syllabus(thread_id, title)

    @mcp.tool()
    def draftGetSyllabusOutline(syllabus_id: str) -> dict:
        """Return the draft syllabus + chapters + lesson titles (no blocks)."""
        return draft_store.outline(syllabus_id)

    @mcp.tool()
    def draftListChapters(syllabus_id: str) -> list[dict]:
        return draft_store.list_chapters(syllabus_id)

    @mcp.tool()
    def draftAddChapter(syllabus_id: str, title: str, summary: Optional[str] = None,
                        position: Optional[int] = None) -> dict:
        return draft_store.add_chapter(syllabus_id, title, summary, position)

    @mcp.tool()
    def draftListLessons(chapter_id: str) -> list[dict]:
        return draft_store.list_lessons(chapter_id)

    @mcp.tool()
    def draftReadLessonBlocks(lesson_id: str) -> dict:
        return draft_store.read_lesson_blocks(lesson_id)

    @mcp.tool()
    def draftAddLesson(chapter_id: str, title: str, blocks: Optional[list[dict]] = None,
                       position: Optional[int] = None, author: Optional[str] = None) -> dict:
        """Create a lesson in the IN-MEMORY DRAFT (not persisted to Supabase)."""
        return draft_store.add_lesson(chapter_id, title, blocks, position, author)

    @mcp.tool()
    def draftUpdateLessonContent(lesson_id: str, blocks: list[dict],
                                 expected_version: Optional[int] = None,
                                 author: Optional[str] = None) -> dict:
        return draft_store.update_lesson_content(lesson_id, blocks, expected_version, author)

    @mcp.tool()
    def draftAppendLessonContent(lesson_id: str, blocks: list[dict],
                                 author: Optional[str] = None) -> dict:
        return draft_store.append_lesson_content(lesson_id, blocks, author)

    @mcp.tool()
    def draftPatchLessonBlocks(lesson_id: str, patches: list[dict],
                               author: Optional[str] = None) -> dict:
        return draft_store.patch_lesson_blocks(lesson_id, patches, author)

    @mcp.tool()
    def draftSnapshot(thread_id: str) -> dict:
        """Return the entire draft (syllabus + chapters + lessons + blocks) for a thread.
        Intended for preview in the UI or as input to a future promote-to-Supabase tool."""
        return draft_store.snapshot(thread_id)

    @mcp.tool()
    def draftReset(thread_id: Optional[str] = None) -> dict:
        """Clear the draft for a thread (or the whole draft store if thread_id is null)."""
        draft_store.reset(thread_id)
        return {"ok": True, "thread_id": thread_id}
