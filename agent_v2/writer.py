"""Writer nodes — lesson & activity. Structured output only. Not in messages."""
from __future__ import annotations
import logging
from typing import Any

from agent.llm import get_llm
from agent_v2.schemas import LessonDraftSchema, ActivityDraftSchema
from agent_v2.state import AgentStateV2

logger = logging.getLogger(__name__)


def _current_substep(state: AgentStateV2):
    plan = state.get("plan") or {}
    ci = state.get("current_chapter_idx", 0)
    si = state.get("current_substep_idx", 0)
    chapters = plan.get("chapters") or []
    if ci >= len(chapters):
        return None, None
    ch = chapters[ci]
    subs = ch.get("substeps") or []
    if si >= len(subs):
        return ch, None
    return ch, subs[si]


def _critic_feedback(state: AgentStateV2) -> str:
    rep = state.get("current_critic") or {}
    if rep and not rep.get("pass_") and rep.get("issues"):
        return "\nPrevious attempt was REJECTED. Fix these issues:\n- " + "\n- ".join(rep["issues"])
    return ""


async def writer_lesson_node(state: AgentStateV2) -> dict[str, Any]:
    ch, sub = _current_substep(state)
    if not sub:
        return {}
    llm = get_llm().with_structured_output(LessonDraftSchema)
    goals = "\n".join(f"- {g}" for g in (sub.get("goals") or []))
    prompt = f"""Write a COMPLETE lesson as BlockNote blocks.

Chapter: {ch.get("title")}
Lesson: {sub.get("title")}
Audience: {(state.get("profile") or {}).get("audience")}
Language: {(state.get("profile") or {}).get("language", "en")}

The lesson MUST cover every goal:
{goals}

BlockNote block types allowed: heading (props.level=1|2|3), paragraph, bulletListItem,
numberedListItem, checkListItem, codeBlock, quote. Each block: {{"type":..., "props":{{"level":2}}?, "content":[{{"type":"text","text":"..."}}]}}.
Required H2 sections in order: "Learning objectives", "Lesson", "Worked example", "Practice", "Summary".
No placeholders, no ellipses, no "TODO". 15+ blocks.{_critic_feedback(state)}"""
    try:
        draft: LessonDraftSchema = await llm.ainvoke(prompt)
        return {
            "current_draft": {"substep_id": sub["id"], "kind": "lesson", **draft.model_dump()},
            "current_attempts": state.get("current_attempts", 0) + 1,
        }
    except Exception as exc:
        logger.exception("writer_lesson failed: %s", exc)
        return {
            "current_draft": {"substep_id": sub["id"], "kind": "lesson", "title": sub.get("title", ""), "blocks": []},
            "current_attempts": state.get("current_attempts", 0) + 1,
        }


async def writer_activity_node(state: AgentStateV2) -> dict[str, Any]:
    ch, sub = _current_substep(state)
    if not sub:
        return {}
    llm = get_llm().with_structured_output(ActivityDraftSchema)
    goals = "\n".join(f"- {g}" for g in (sub.get("goals") or []))
    prompt = f"""Write ONE quiz question as a structured activity.

Chapter: {ch.get("title")}
Activity goal: {sub.get("title")}
Must assess these concepts:
{goals}

- 3-5 options.
- multi=false for single-choice, multi=true for multi-correct.
- correct_index is an int if multi=false, else a list[int].
- Include a short `explanation`.{_critic_feedback(state)}"""
    try:
        draft: ActivityDraftSchema = await llm.ainvoke(prompt)
        return {
            "current_draft": {"substep_id": sub["id"], "kind": "activity", **draft.model_dump()},
            "current_attempts": state.get("current_attempts", 0) + 1,
        }
    except Exception as exc:
        logger.exception("writer_activity failed: %s", exc)
        return {
            "current_draft": {"substep_id": sub["id"], "kind": "activity", "question": sub.get("title", ""), "options": ["A", "B"], "correct_index": 0, "multi": False, "explanation": ""},
            "current_attempts": state.get("current_attempts", 0) + 1,
        }
