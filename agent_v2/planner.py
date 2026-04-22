"""Planner node: turns profile + research notes into a concrete Plan.

One forced structured-output LLM call. Emits one `setPlan` interrupt so the UI
shows progress, but it is not required for the graph to advance.
"""
from __future__ import annotations
import logging
from typing import Any

from langgraph.types import interrupt

from agent.llm import get_llm
from agent_v2.schemas import PlanSchema
from agent_v2.state import AgentStateV2

logger = logging.getLogger(__name__)


async def planner_node(state: AgentStateV2) -> dict[str, Any]:
    profile = state.get("profile") or {}
    llm = get_llm().with_structured_output(PlanSchema)

    prompt = f"""You are a curriculum designer. Produce a DETAILED plan for:
Topic: {profile.get("topic")!r}
Audience: {profile.get("audience")!r}
Language: {profile.get("language", "en")}
Chapters expected: {profile.get("num_chapters", 3)}
Approved chapter titles (use verbatim if provided): {profile.get("chapter_titles") or "auto"}
Activities per chapter: {profile.get("activities_per_chapter", 1)}
Research notes to ground goals:
{chr(10).join("- " + n for n in (profile.get("research_notes") or []))}

RULES:
- Each chapter has 2-5 lesson substeps THEN {profile.get("activities_per_chapter", 1)} activity substep(s) at the END.
- Every substep MUST list 3-6 concrete `goals` — the critic will grade against them verbatim.
- substep.id = "ch{{n}}-l{{m}}" for lessons, "ch{{n}}-a{{k}}" for activities.
- chapter.id = "ch{{n}}".
Return the schema exactly."""

    try:
        plan_obj: PlanSchema = await llm.ainvoke(prompt)
        plan = plan_obj.model_dump()
    except Exception as exc:
        logger.exception("planner structured output failed: %s", exc)
        # Fallback minimal plan from chapter_titles so graph still advances
        titles = profile.get("chapter_titles") or [f"Chapter {i+1}" for i in range(profile.get("num_chapters", 3))]
        plan = {
            "topic": profile.get("topic", ""),
            "audience": profile.get("audience", ""),
            "language": profile.get("language", "en"),
            "chapters": [
                {
                    "id": f"ch{i+1}",
                    "title": t,
                    "summary": "",
                    "substeps": [
                        {"id": f"ch{i+1}-l1", "kind": "lesson", "title": f"{t} — Lesson 1", "goals": ["Introduce the topic"]},
                        {"id": f"ch{i+1}-a1", "kind": "activity", "title": f"{t} — Quiz", "goals": ["Check comprehension"]},
                    ],
                }
                for i, t in enumerate(titles)
            ],
        }

    # mark everything undone
    for ch in plan["chapters"]:
        ch["done"] = False
        for s in ch["substeps"]:
            s["done"] = False

    # Publish to UI as a flat plan (one interrupt, fire-and-forget)
    try:
        interrupt({
            "type": "setPlan",
            "items": [
                {"id": s["id"], "title": f"[{ch['title']}] {s['title']}", "status": "pending"}
                for ch in plan["chapters"] for s in ch["substeps"]
            ],
        })
    except Exception:
        pass

    return {"plan": plan, "current_chapter_idx": 0, "current_substep_idx": 0}
