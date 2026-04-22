"""Info gathering: hidden web-search subgraph + single askUser interrupt.

Flow:
  1. read the latest human message (topic hint)
  2. plan 3 short search queries via LLM (structured)
  3. run serper queries in parallel, cache results in state.research_cache (internal)
  4. ask LLM to produce ResearchRecommendationSchema
  5. emit ONE interrupt({type: "askUser", questions:[...]}) with suggested choices
  6. on resume, save profile, CLEAR research_cache
"""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from agent.llm import get_llm
from agent.search import run_search_step
from agent_v2.schemas import ResearchRecommendationSchema
from agent_v2.state import AgentStateV2

logger = logging.getLogger(__name__)


def _last_user_text(state: AgentStateV2) -> str:
    for m in reversed(state.get("messages") or []):
        if getattr(m, "type", None) == "human" or m.__class__.__name__ == "HumanMessage":
            return str(getattr(m, "content", "") or "")
    return ""


async def info_gather_node(state: AgentStateV2) -> dict[str, Any]:
    user_hint = _last_user_text(state) or "a short syllabus"
    llm = get_llm()

    # 1) plan queries (small, one call, throw-away)
    q_prompt = (
        "User wants a syllabus on: %r. Produce 3 short Google queries to research "
        "an authoritative beginner curriculum. Return ONLY a JSON list of strings." % user_hint
    )
    try:
        raw = (await llm.ainvoke([HumanMessage(content=q_prompt)])).content
        import json, re
        m = re.search(r"\[.*?\]", str(raw), re.S)
        queries = json.loads(m.group(0)) if m else [user_hint]
        queries = [str(q) for q in queries][:3] or [user_hint]
    except Exception:
        queries = [f"{user_hint} beginner syllabus", f"{user_hint} learning roadmap"]

    # 2) run search (internal only)
    try:
        research = await run_search_step(queries, top_per_query=3)
    except Exception as exc:
        logger.warning("search failed: %s", exc)
        research = []

    # 3) ask LLM for structured recommendation
    structured = llm.with_structured_output(ResearchRecommendationSchema)
    ctx = "\n".join(
        f"- {item.get('query')}: "
        + ", ".join((item.get("result_urls") or [])[:3])
        for item in research
    )
    reco_prompt = (
        f"Based on this quick research, recommend a beginner syllabus plan for: {user_hint!r}.\n"
        f"Research notes:\n{ctx}\n"
        "Respect the schema exactly."
    )
    try:
        reco: ResearchRecommendationSchema = await structured.ainvoke(reco_prompt)
    except Exception:
        reco = ResearchRecommendationSchema(
            suggested_topic=user_hint,
            suggested_audience="beginner",
            suggested_language="en",
            recommended_chapter_titles=[f"Introduction to {user_hint}", f"Core concepts", f"Practice"],
            notes=[],
        )

    # 4) ONE interrupt to the user — no chat messages. The frontend already renders
    #    an "askUser" card from this interrupt payload shape.
    answers = interrupt({
        "type": "askUser",
        "questions": [
            {"id": "topic", "prompt": "Confirm the topic", "choices": [reco.suggested_topic], "allow_custom": True},
            {"id": "audience", "prompt": "Who is this for?", "choices": [reco.suggested_audience, "beginner", "intermediate", "advanced"], "allow_custom": True},
            {"id": "language", "prompt": "Language", "choices": [reco.suggested_language, "en", "fr", "ar"], "allow_custom": True},
            {"id": "num_chapters", "prompt": "How many chapters?", "choices": ["3", "5", "7"], "allow_custom": True},
            {"id": "chapter_titles", "prompt": "Accept these chapter titles?", "choices": reco.recommended_chapter_titles, "multi": True, "allow_custom": True},
            {"id": "activities_per_chapter", "prompt": "Quiz activities per chapter?", "choices": ["0", "1", "2", "3"], "allow_custom": True},
        ],
    })

    ans = (answers or {}).get("answers") if isinstance(answers, dict) else (answers or {})
    profile = {
        "topic": ans.get("topic") or reco.suggested_topic,
        "audience": ans.get("audience") or reco.suggested_audience,
        "language": ans.get("language") or reco.suggested_language,
        "num_chapters": int(str(ans.get("num_chapters") or len(reco.recommended_chapter_titles) or 3).strip() or 3),
        "chapter_titles": ans.get("chapter_titles") or reco.recommended_chapter_titles,
        "activities_per_chapter": int(str(ans.get("activities_per_chapter") or 1).strip() or 1),
        "research_notes": reco.notes,
    }

    # 5) drop research_cache — we already distilled it into profile.research_notes
    return {"profile": profile, "research_cache": []}
