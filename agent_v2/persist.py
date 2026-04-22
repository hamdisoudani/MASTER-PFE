"""Persist a passed draft via curriculum-mcp (or Supabase direct fallback), then
clear transient fields and advance to the next substep.

This is where we DROP the writer/critic buffers so the checkpoint does not grow.
"""
from __future__ import annotations
import logging
from typing import Any

from agent_v2.state import AgentStateV2
from agent_v2.router import advance_indices

logger = logging.getLogger(__name__)


async def _persist_lesson(state: AgentStateV2, draft: dict) -> str | None:
    try:
        from agent.mcp_client import load_curriculum_tools
    except Exception:
        return None
    try:
        tools = await load_curriculum_tools()
    except Exception as exc:
        logger.warning("mcp load failed: %s", exc)
        return None
    by_name = {getattr(t, "name", ""): t for t in (tools or [])}
    syllabus_id = state.get("draft_syllabus_id")
    if not syllabus_id:
        get_or_create = by_name.get("draftGetOrCreateSyllabus") or by_name.get("getOrCreateSyllabus")
        if get_or_create:
            try:
                res = await get_or_create.ainvoke({"topic": (state.get("profile") or {}).get("topic", "syllabus")})
                syllabus_id = (res or {}).get("id") if isinstance(res, dict) else None
            except Exception as exc:
                logger.warning("syllabus create failed: %s", exc)

    add = by_name.get("addLesson") or by_name.get("draftAddLesson")
    if not add:
        return None
    try:
        res = await add.ainvoke({
            "syllabusId": syllabus_id,
            "chapterId": draft.get("substep_id", "").split("-")[0],
            "title": draft.get("title"),
            "content": draft.get("blocks"),
        })
        return (res or {}).get("id") if isinstance(res, dict) else None
    except Exception as exc:
        logger.warning("addLesson failed: %s", exc)
        return None


async def _persist_activity(state: AgentStateV2, draft: dict) -> str | None:
    # curriculum-mcp may not have addActivity yet — swallow failures gracefully.
    try:
        from agent.mcp_client import load_curriculum_tools
        tools = await load_curriculum_tools()
    except Exception:
        return None
    by_name = {getattr(t, "name", ""): t for t in (tools or [])}
    add = by_name.get("addActivity") or by_name.get("draftAddActivity")
    if not add:
        logger.info("addActivity tool not available; skipping persist for activity")
        return None
    try:
        res = await add.ainvoke({
            "syllabusId": state.get("draft_syllabus_id"),
            "chapterId": draft.get("substep_id", "").split("-")[0],
            "activity": {
                "question": draft.get("question"),
                "options": draft.get("options"),
                "correct_index": draft.get("correct_index"),
                "multi": draft.get("multi"),
                "explanation": draft.get("explanation"),
            },
        })
        return (res or {}).get("id") if isinstance(res, dict) else None
    except Exception as exc:
        logger.warning("addActivity failed: %s", exc)
        return None


async def persist_node(state: AgentStateV2) -> dict[str, Any]:
    draft = state.get("current_draft") or {}
    plan = state.get("plan") or {}
    chapters = [dict(c) for c in (plan.get("chapters") or [])]
    ci = state.get("current_chapter_idx", 0)
    si = state.get("current_substep_idx", 0)

    persisted_id: str | None = None
    if draft.get("kind") == "lesson":
        persisted_id = await _persist_lesson(state, draft)
    elif draft.get("kind") == "activity":
        persisted_id = await _persist_activity(state, draft)

    if ci < len(chapters):
        subs = [dict(s) for s in (chapters[ci].get("substeps") or [])]
        if si < len(subs):
            subs[si] = {**subs[si], "done": True, "persisted_id": persisted_id}
        chapters[ci] = {**chapters[ci], "substeps": subs}

    delta = {
        "plan": {**plan, "chapters": chapters},
        "current_draft": None,
        "current_critic": None,
        "current_attempts": 0,
    }
    # Advance indices
    adv = advance_indices({**state, **delta})
    delta.update(adv)
    return delta


async def escalate_node(state: AgentStateV2) -> dict[str, Any]:
    """Max revisions hit. Mark substep done with the last draft and move on — we
    do NOT block the pipeline on quality failures; the UI can flag the attempt."""
    logger.warning("critic exhausted on substep — proceeding with last draft")
    return await persist_node(state)


async def promote_node(state: AgentStateV2) -> dict[str, Any]:
    try:
        from agent.mcp_client import load_curriculum_tools
        tools = await load_curriculum_tools()
        by_name = {getattr(t, "name", ""): t for t in (tools or [])}
        promote = by_name.get("draftPromote") or by_name.get("promoteDraft")
        if promote:
            await promote.ainvoke({"syllabusId": state.get("draft_syllabus_id")})
    except Exception as exc:
        logger.warning("promote failed: %s", exc)
    return {"stop_reason": "completed"}
