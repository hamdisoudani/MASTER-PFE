"""MCP tool implementations. Each tool maps 1:1 to a curriculum mutation/read.

Every tool is wrapped so Supabase/validation errors are NEVER raised back
through the MCP transport (which would otherwise tear down the session and
surface a useless stack trace to the agent). Instead we return a structured
envelope:

    {"ok": true,  "data": <payload>}
or
    {"ok": false, "error": {"code": "<machine-code>", "message": "<human>",
                            "hint": "<optional next step for the agent>"}}

This lets the agent reason about failures (bad id, version conflict, missing
parent) and self-correct, instead of crashing the MCP server or entering a
retry loop on opaque 500s.

Security / integrity guarantees enforced here (independent of the model):
  * You cannot create a chapter without a real syllabus_id.
  * You cannot create a lesson without a real chapter_id.
  * You cannot read / append / update / patch a lesson that does not exist.
  * Every id must be a well-formed UUID.
  * BlockNote payloads must be a JSON array (not a string / not prose).
"""
from __future__ import annotations
import logging
import uuid
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
from .db import client
from .models import BlockPatch

logger = logging.getLogger(__name__)


# ---------- envelope helpers -----------------------------------------------

def _ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def _err(code: str, message: str, hint: Optional[str] = None) -> dict:
    env = {"ok": False, "error": {"code": code, "message": message}}
    if hint:
        env["error"]["hint"] = hint
    return env


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _require_uuid(value: Any, field: str) -> Optional[dict]:
    if not _is_uuid(value):
        return _err(
            "invalid_id",
            f"{field} is not a valid UUID: {value!r}",
            hint=f"Call the relevant list/outline tool to discover a real {field}.",
        )
    return None


def _require_blocks_list(value: Any, field: str = "blocks") -> Optional[dict]:
    if not isinstance(value, list):
        return _err(
            "invalid_blocks",
            f"{field} must be a JSON array of BlockNote blocks, got {type(value).__name__}.",
            hint="Pass a real JSON array like [{type:'heading',...}, {type:'paragraph',...}].",
        )
    for i, b in enumerate(value):
        if not isinstance(b, dict) or "type" not in b:
            return _err(
                "invalid_blocks",
                f"{field}[{i}] is not a valid BlockNote block (missing 'type').",
            )
    return None


def register(mcp: FastMCP) -> None:

    # ---------- read-only / bootstrap --------------------------------------

    @mcp.tool()
    def getOrCreateSyllabus(thread_id: str, title: Optional[str] = None) -> dict:
        """Return the syllabus for a thread, creating it if missing.

        This is the FIRST tool you must call at the start of any authoring
        session. The returned `id` is the `syllabus_id` you pass to
        addChapter. Never invent a syllabus_id.
        """
        try:
            if not isinstance(thread_id, str) or not thread_id.strip():
                return _err("invalid_input", "thread_id must be a non-empty string.")
            sb = client()
            existing = (
                sb.table("syllabi").select("*").eq("thread_id", thread_id).limit(1).execute()
            )
            if existing.data:
                return _ok(existing.data[0])
            inserted = sb.table("syllabi").insert({
                "thread_id": thread_id,
                "title": (title or "Untitled syllabus")[:200],
            }).execute()
            return _ok(inserted.data[0])
        except Exception as e:
            logger.exception("getOrCreateSyllabus failed")
            return _err("db_error", f"getOrCreateSyllabus failed: {e}")

    @mcp.tool()
    def getSyllabusOutline(syllabus_id: str) -> dict:
        """Return syllabus + chapters + lesson titles (no blocks).

        Use this to DISCOVER real chapter_ids and lesson_ids before any
        mutation. Do NOT invent ids.
        """
        bad = _require_uuid(syllabus_id, "syllabus_id")
        if bad: return bad
        try:
            sb = client()
            syl_row = sb.table("syllabi").select("*").eq("id", syllabus_id).limit(1).execute()
            if not syl_row.data:
                return _err(
                    "syllabus_not_found",
                    f"No syllabus with id {syllabus_id}.",
                    hint="Call getOrCreateSyllabus(thread_id) first.",
                )
            syl = syl_row.data[0]
            chapters = (
                sb.table("chapters").select("*").eq("syllabus_id", syllabus_id)
                .order("position").execute().data
            )
            for ch in chapters:
                ch["lessons"] = (
                    sb.table("lessons")
                    .select("id,position,title,block_count,version,updated_at")
                    .eq("chapter_id", ch["id"]).order("position").execute().data
                )
            syl["chapters"] = chapters
            return _ok(syl)
        except Exception as e:
            logger.exception("getSyllabusOutline failed")
            return _err("db_error", f"getSyllabusOutline failed: {e}")

    @mcp.tool()
    def listChapters(syllabus_id: str) -> dict:
        bad = _require_uuid(syllabus_id, "syllabus_id")
        if bad: return bad
        try:
            rows = (
                client().table("chapters").select("*").eq("syllabus_id", syllabus_id)
                .order("position").execute().data
            )
            return _ok(rows)
        except Exception as e:
            logger.exception("listChapters failed")
            return _err("db_error", f"listChapters failed: {e}")

    @mcp.tool()
    def listLessons(chapter_id: str) -> dict:
        bad = _require_uuid(chapter_id, "chapter_id")
        if bad: return bad
        try:
            rows = (
                client().table("lessons").select("*").eq("chapter_id", chapter_id)
                .order("position").execute().data
            )
            return _ok(rows)
        except Exception as e:
            logger.exception("listLessons failed")
            return _err("db_error", f"listLessons failed: {e}")

    @mcp.tool()
    def readLessonBlocks(lesson_id: str) -> dict:
        bad = _require_uuid(lesson_id, "lesson_id")
        if bad: return bad
        try:
            row = (
                client().table("lessons").select("id,title,blocks,version")
                .eq("id", lesson_id).limit(1).execute().data
            )
            if not row:
                return _err(
                    "lesson_not_found",
                    f"No lesson with id {lesson_id}.",
                    hint="Call getSyllabusOutline or listLessons to find real lesson ids.",
                )
            return _ok(row[0])
        except Exception as e:
            logger.exception("readLessonBlocks failed")
            return _err("db_error", f"readLessonBlocks failed: {e}")

    # ---------- mutations (with parent-existence guardrails) ---------------

    @mcp.tool()
    def addChapter(syllabus_id: str, title: str, summary: Optional[str] = None,
                   position: Optional[int] = None) -> dict:
        """Create a chapter under an EXISTING syllabus. Fails cleanly if
        the syllabus does not exist (no orphan chapters)."""
        bad = _require_uuid(syllabus_id, "syllabus_id")
        if bad: return bad
        if not isinstance(title, str) or not title.strip():
            return _err("invalid_input", "title must be a non-empty string.")
        try:
            sb = client()
            syl = (
                sb.table("syllabi").select("id").eq("id", syllabus_id).limit(1).execute().data
            )
            if not syl:
                return _err(
                    "syllabus_not_found",
                    f"Cannot add chapter: syllabus {syllabus_id} does not exist.",
                    hint="Call getOrCreateSyllabus(thread_id) first and reuse the returned id.",
                )
            if position is None:
                existing = (
                    sb.table("chapters").select("position").eq("syllabus_id", syllabus_id)
                    .order("position", desc=True).limit(1).execute().data
                )
                position = (existing[0]["position"] + 1) if existing else 0
            row = sb.table("chapters").insert({
                "syllabus_id": syllabus_id,
                "title": title.strip(),
                "summary": summary,
                "position": position,
            }).execute().data[0]
            return _ok(row)
        except Exception as e:
            logger.exception("addChapter failed")
            return _err("db_error", f"addChapter failed: {e}")

    @mcp.tool()
    def addLesson(chapter_id: str, title: str, blocks: Optional[list[dict]] = None,
                  position: Optional[int] = None, author: Optional[str] = None) -> dict:
        """Create a lesson under an EXISTING chapter.

        Enforces: chapter_id must be a real UUID, the chapter must exist,
        and its parent syllabus must exist. Blocks (if provided) must be a
        proper JSON array of BlockNote blocks.
        """
        bad = _require_uuid(chapter_id, "chapter_id")
        if bad: return bad
        if not isinstance(title, str) or not title.strip():
            return _err("invalid_input", "title must be a non-empty string.")
        if blocks is not None:
            bad = _require_blocks_list(blocks, "blocks")
            if bad: return bad
        try:
            sb = client()
            chap = (
                sb.table("chapters").select("id,syllabus_id")
                .eq("id", chapter_id).limit(1).execute().data
            )
            if not chap:
                return _err(
                    "chapter_not_found",
                    f"Cannot add lesson: chapter {chapter_id} does not exist.",
                    hint="Call getSyllabusOutline(syllabus_id) or addChapter(...) first; "
                         "never invent chapter_ids.",
                )
            syl = (
                sb.table("syllabi").select("id").eq("id", chap[0]["syllabus_id"])
                .limit(1).execute().data
            )
            if not syl:
                return _err(
                    "orphan_chapter",
                    f"Chapter {chapter_id} points to a missing syllabus; aborting.",
                )
            if position is None:
                existing = (
                    sb.table("lessons").select("position").eq("chapter_id", chapter_id)
                    .order("position", desc=True).limit(1).execute().data
                )
                position = (existing[0]["position"] + 1) if existing else 0
            row = sb.table("lessons").insert({
                "chapter_id": chapter_id,
                "title": title.strip(),
                "blocks": blocks or [],
                "position": position,
                "last_author": author,
            }).execute().data[0]
            try:
                sb.table("lesson_edits").insert({
                    "lesson_id": row["id"], "op": "add",
                    "patch": {"title": title, "blocks": blocks or []},
                    "to_version": row["version"], "author": author,
                }).execute()
            except Exception:
                logger.exception("addLesson: audit insert failed (non-fatal)")
            return _ok(row)
        except Exception as e:
            logger.exception("addLesson failed")
            return _err("db_error", f"addLesson failed: {e}")

    @mcp.tool()
    def updateLessonContent(lesson_id: str, blocks: list[dict],
                            expected_version: Optional[int] = None,
                            author: Optional[str] = None) -> dict:
        bad = _require_uuid(lesson_id, "lesson_id")
        if bad: return bad
        bad = _require_blocks_list(blocks, "blocks")
        if bad: return bad
        try:
            sb = client()
            cur = (
                sb.table("lessons").select("version").eq("id", lesson_id)
                .limit(1).execute().data
            )
            if not cur:
                return _err(
                    "lesson_not_found",
                    f"Cannot update: lesson {lesson_id} does not exist.",
                    hint="Discover real lesson_ids via getSyllabusOutline first.",
                )
            current = cur[0]
            if expected_version is not None and current["version"] != expected_version:
                return _err(
                    "version_conflict",
                    f"version conflict: expected {expected_version}, actual {current['version']}.",
                    hint="Re-read the lesson with readLessonBlocks and retry with the fresh version.",
                )
            updated = (
                sb.table("lessons").update({"blocks": blocks, "last_author": author})
                .eq("id", lesson_id).execute().data[0]
            )
            try:
                sb.table("lesson_edits").insert({
                    "lesson_id": lesson_id, "op": "update",
                    "patch": {"blocks": blocks},
                    "from_version": current["version"], "to_version": updated["version"],
                    "author": author,
                }).execute()
            except Exception:
                logger.exception("updateLessonContent: audit insert failed (non-fatal)")
            return _ok(updated)
        except Exception as e:
            logger.exception("updateLessonContent failed")
            return _err("db_error", f"updateLessonContent failed: {e}")

    @mcp.tool()
    def appendLessonContent(lesson_id: str, blocks: list[dict],
                            author: Optional[str] = None) -> dict:
        bad = _require_uuid(lesson_id, "lesson_id")
        if bad: return bad
        bad = _require_blocks_list(blocks, "blocks")
        if bad: return bad
        try:
            sb = client()
            cur = (
                sb.table("lessons").select("blocks,version").eq("id", lesson_id)
                .limit(1).execute().data
            )
            if not cur:
                return _err(
                    "lesson_not_found",
                    f"Cannot append: lesson {lesson_id} does not exist.",
                    hint="Call addLesson first and reuse the returned id in every appendLessonContent.",
                )
            current = cur[0]
            new_blocks = (current["blocks"] or []) + blocks
            updated = (
                sb.table("lessons").update({"blocks": new_blocks, "last_author": author})
                .eq("id", lesson_id).execute().data[0]
            )
            try:
                sb.table("lesson_edits").insert({
                    "lesson_id": lesson_id, "op": "append",
                    "patch": {"blocks": blocks},
                    "from_version": current["version"], "to_version": updated["version"],
                    "author": author,
                }).execute()
            except Exception:
                logger.exception("appendLessonContent: audit insert failed (non-fatal)")
            return _ok(updated)
        except Exception as e:
            logger.exception("appendLessonContent failed")
            return _err("db_error", f"appendLessonContent failed: {e}")

    @mcp.tool()
    def patchLessonBlocks(lesson_id: str, patches: list[dict],
                          author: Optional[str] = None) -> dict:
        """Apply surgical patches by BlockNote block id."""
        bad = _require_uuid(lesson_id, "lesson_id")
        if bad: return bad
        if not isinstance(patches, list) or not patches:
            return _err("invalid_input", "patches must be a non-empty JSON array.")
        try:
            sb = client()
            cur = (
                sb.table("lessons").select("blocks,version").eq("id", lesson_id)
                .limit(1).execute().data
            )
            if not cur:
                return _err(
                    "lesson_not_found",
                    f"Cannot patch: lesson {lesson_id} does not exist.",
                )
            current = cur[0]
            blocks: list[dict] = list(current["blocks"] or [])
            for raw in patches:
                try:
                    p = BlockPatch.model_validate(raw)
                except Exception as ve:
                    return _err(
                        "invalid_patch",
                        f"Invalid patch entry: {ve}",
                        hint="Each patch needs op in {replace,insert_after,insert_before,delete} + block_id.",
                    )
                idx = next((i for i, b in enumerate(blocks) if b.get("id") == p.block_id), -1)
                if idx < 0 and p.op not in ("insert_after", "insert_before"):
                    return _err(
                        "block_not_found",
                        f"block {p.block_id} not found in lesson {lesson_id}.",
                        hint="Call readLessonBlocks to see current block ids.",
                    )
                if p.op == "replace":
                    blocks[idx] = p.block or blocks[idx]
                elif p.op == "delete":
                    blocks.pop(idx)
                elif p.op == "insert_after":
                    if not p.block:
                        return _err("invalid_patch", "insert_after requires 'block'.")
                    blocks.insert(idx + 1 if idx >= 0 else len(blocks), p.block)
                elif p.op == "insert_before":
                    if not p.block:
                        return _err("invalid_patch", "insert_before requires 'block'.")
                    blocks.insert(idx if idx >= 0 else 0, p.block)
            updated = (
                sb.table("lessons").update({"blocks": blocks, "last_author": author})
                .eq("id", lesson_id).execute().data[0]
            )
            try:
                sb.table("lesson_edits").insert({
                    "lesson_id": lesson_id, "op": "patch",
                    "patch": {"patches": patches},
                    "from_version": current["version"], "to_version": updated["version"],
                    "author": author,
                }).execute()
            except Exception:
                logger.exception("patchLessonBlocks: audit insert failed (non-fatal)")
            return _ok(updated)
        except Exception as e:
            logger.exception("patchLessonBlocks failed")
            return _err("db_error", f"patchLessonBlocks failed: {e}")
