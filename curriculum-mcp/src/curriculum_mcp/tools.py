"""MCP tool implementations. Each tool maps 1:1 to a curriculum mutation/read."""
from __future__ import annotations
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
from .db import client
from .models import BlockPatch


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def getOrCreateSyllabus(thread_id: str, title: Optional[str] = None) -> dict:
        """Return the syllabus for a thread, creating it if missing."""
        sb = client()
        existing = sb.table("syllabi").select("*").eq("thread_id", thread_id).limit(1).execute()
        if existing.data:
            return existing.data[0]
        inserted = sb.table("syllabi").insert({
            "thread_id": thread_id,
            "title": title or "Untitled syllabus",
        }).execute()
        return inserted.data[0]

    @mcp.tool()
    def getSyllabusOutline(syllabus_id: str) -> dict:
        """Return syllabus + chapters + lesson titles (no blocks)."""
        sb = client()
        syl = sb.table("syllabi").select("*").eq("id", syllabus_id).single().execute().data
        chapters = sb.table("chapters").select("*").eq("syllabus_id", syllabus_id)            .order("position").execute().data
        for ch in chapters:
            ch["lessons"] = sb.table("lessons")                .select("id,position,title,block_count,version,updated_at")                .eq("chapter_id", ch["id"]).order("position").execute().data
            try:
                ch["activities"] = sb.table("activities")                    .select("id,position,kind,title,updated_at")                    .eq("chapter_id", ch["id"]).order("position").execute().data
            except Exception:
                ch["activities"] = []
        syl["chapters"] = chapters
        return syl

    @mcp.tool()
    def listChapters(syllabus_id: str) -> list[dict]:
        return client().table("chapters").select("*").eq("syllabus_id", syllabus_id)            .order("position").execute().data

    @mcp.tool()
    def addChapter(syllabus_id: str, title: str, summary: Optional[str] = None,
                   position: Optional[int] = None) -> dict:
        sb = client()
        if position is None:
            existing = sb.table("chapters").select("position").eq("syllabus_id", syllabus_id)                .order("position", desc=True).limit(1).execute().data
            position = (existing[0]["position"] + 1) if existing else 0
        return sb.table("chapters").insert({
            "syllabus_id": syllabus_id, "title": title,
            "summary": summary, "position": position,
        }).execute().data[0]

    @mcp.tool()
    def listLessons(chapter_id: str) -> list[dict]:
        return client().table("lessons").select("*").eq("chapter_id", chapter_id)            .order("position").execute().data

    @mcp.tool()
    def readLessonBlocks(lesson_id: str) -> dict:
        row = client().table("lessons").select("id,title,blocks,version")            .eq("id", lesson_id).single().execute().data
        return row

    @mcp.tool()
    def addLesson(chapter_id: str, title: str, blocks: Optional[list[dict]] = None,
                  position: Optional[int] = None, author: Optional[str] = None) -> dict:
        sb = client()
        if position is None:
            existing = sb.table("lessons").select("position").eq("chapter_id", chapter_id)                .order("position", desc=True).limit(1).execute().data
            position = (existing[0]["position"] + 1) if existing else 0
        row = sb.table("lessons").insert({
            "chapter_id": chapter_id, "title": title,
            "blocks": blocks or [], "position": position, "last_author": author,
        }).execute().data[0]
        sb.table("lesson_edits").insert({
            "lesson_id": row["id"], "op": "add", "patch": {"title": title, "blocks": blocks or []},
            "to_version": row["version"], "author": author,
        }).execute()
        return row

    @mcp.tool()
    def updateLessonContent(lesson_id: str, blocks: list[dict],
                            expected_version: Optional[int] = None,
                            author: Optional[str] = None) -> dict:
        sb = client()
        current = sb.table("lessons").select("version").eq("id", lesson_id).single().execute().data
        if expected_version is not None and current["version"] != expected_version:
            raise ValueError(
                f"version conflict: expected {expected_version}, actual {current['version']}"
            )
        updated = sb.table("lessons").update({"blocks": blocks, "last_author": author})            .eq("id", lesson_id).execute().data[0]
        sb.table("lesson_edits").insert({
            "lesson_id": lesson_id, "op": "update", "patch": {"blocks": blocks},
            "from_version": current["version"], "to_version": updated["version"], "author": author,
        }).execute()
        return updated

    @mcp.tool()
    def appendLessonContent(lesson_id: str, blocks: list[dict],
                            author: Optional[str] = None) -> dict:
        sb = client()
        current = sb.table("lessons").select("blocks,version").eq("id", lesson_id)            .single().execute().data
        new_blocks = (current["blocks"] or []) + blocks
        updated = sb.table("lessons").update({"blocks": new_blocks, "last_author": author})            .eq("id", lesson_id).execute().data[0]
        sb.table("lesson_edits").insert({
            "lesson_id": lesson_id, "op": "append", "patch": {"blocks": blocks},
            "from_version": current["version"], "to_version": updated["version"], "author": author,
        }).execute()
        return updated

    @mcp.tool()
    def patchLessonBlocks(lesson_id: str, patches: list[dict],
                          author: Optional[str] = None) -> dict:
        """Apply surgical patches by BlockNote block id."""
        sb = client()
        current = sb.table("lessons").select("blocks,version").eq("id", lesson_id)            .single().execute().data
        blocks: list[dict] = list(current["blocks"] or [])
        for raw in patches:
            p = BlockPatch.model_validate(raw)
            idx = next((i for i, b in enumerate(blocks) if b.get("id") == p.block_id), -1)
            if idx < 0 and p.op != "insert_after" and p.op != "insert_before":
                raise ValueError(f"block {p.block_id} not found")
            if p.op == "replace":
                blocks[idx] = p.block or blocks[idx]
            elif p.op == "delete":
                blocks.pop(idx)
            elif p.op == "insert_after":
                if not p.block:
                    raise ValueError("insert_after requires 'block'")
                blocks.insert(idx + 1 if idx >= 0 else len(blocks), p.block)
            elif p.op == "insert_before":
                if not p.block:
                    raise ValueError("insert_before requires 'block'")
                blocks.insert(idx if idx >= 0 else 0, p.block)
        updated = sb.table("lessons").update({"blocks": blocks, "last_author": author})            .eq("id", lesson_id).execute().data[0]
        sb.table("lesson_edits").insert({
            "lesson_id": lesson_id, "op": "patch", "patch": {"patches": patches},
            "from_version": current["version"], "to_version": updated["version"], "author": author,
        }).execute()
        return updated

    @mcp.tool()
    def listChapterActivities(chapter_id: str) -> list[dict]:
        """List persisted activities for a chapter (full payload incl. answer keys)."""
        return client().table("activities").select("*")            .eq("chapter_id", chapter_id).order("position").execute().data

    @mcp.tool()
    def getActivity(activity_id: str) -> dict:
        """Fetch a single persisted activity by id."""
        return client().table("activities").select("*")            .eq("id", activity_id).single().execute().data

    @mcp.tool()
    def addChapterActivity(chapter_id: str, kind: str, title: str, payload: dict,
                           position: Optional[int] = None) -> dict:
        """Persist a chapter-level activity (currently kind='quiz').

        The payload carries the authoritative answer key — see
        ``draftAddActivity`` in draft_tools.py for the quiz schema. Frontend
        verification compares the learner's choice ids to
        ``correct_choice_ids``.
        """
        sb = client()
        if position is None:
            existing = sb.table("activities").select("position")                .eq("chapter_id", chapter_id)                .order("position", desc=True).limit(1).execute().data
            position = (existing[0]["position"] + 1) if existing else 0
        return sb.table("activities").insert({
            "chapter_id": chapter_id, "kind": kind, "title": title,
            "payload": payload, "position": position,
        }).execute().data[0]

    @mcp.tool()
    def updateChapterActivity(activity_id: str, payload: dict,
                              title: Optional[str] = None) -> dict:
        """Full-overwrite a persisted activity's payload (and optionally title)."""
        update: dict[str, Any] = {"payload": payload}
        if title is not None:
            update["title"] = title
        return client().table("activities").update(update)            .eq("id", activity_id).execute().data[0]
