"""Deterministic router. The LLM never picks the next step."""
from __future__ import annotations
from typing import Any

from agent_v2.state import AgentStateV2


def _current(state: AgentStateV2) -> tuple[int, int, dict | None, dict | None]:
    plan = state.get("plan") or {}
    chapters = plan.get("chapters") or []
    ci = state.get("current_chapter_idx", 0)
    si = state.get("current_substep_idx", 0)
    if ci >= len(chapters):
        return ci, si, None, None
    ch = chapters[ci]
    subs = ch.get("substeps") or []
    sub = subs[si] if si < len(subs) else None
    return ci, si, ch, sub


def advance_indices(state: AgentStateV2) -> dict[str, Any]:
    """Return a state delta that moves to the next undone substep, marking
    chapters done as their substeps complete. Idempotent."""
    plan = state.get("plan") or {}
    chapters = list(plan.get("chapters") or [])
    ci = state.get("current_chapter_idx", 0)
    si = state.get("current_substep_idx", 0) + 1
    while ci < len(chapters):
        subs = chapters[ci].get("substeps") or []
        while si < len(subs) and subs[si].get("done"):
            si += 1
        if si < len(subs):
            return {"current_chapter_idx": ci, "current_substep_idx": si}
        chapters[ci] = {**chapters[ci], "done": True}
        ci += 1
        si = 0
    return {
        "plan": {**plan, "chapters": chapters},
        "current_chapter_idx": ci,
        "current_substep_idx": 0,
        "stop_reason": "completed",
    }


def route_after_router(state: AgentStateV2) -> str:
    """Entry gate. Returns node name."""
    if not state.get("profile"):
        return "info_gather"
    if not state.get("plan"):
        return "planner"
    ci, si, ch, sub = _current(state)
    if sub is None:
        return "promote"
    if sub.get("done"):
        return "advance"
    kind = sub.get("kind")
    return "writer_lesson" if kind == "lesson" else "writer_activity"


def route_after_critic(state: AgentStateV2) -> str:
    report = state.get("current_critic") or {}
    attempts = state.get("current_attempts", 0)
    if report.get("pass_"):
        return "persist"
    if attempts >= int(__import__("os").getenv("V2_MAX_REVISIONS", "2")):
        return "escalate"
    ci, si, ch, sub = _current(state)
    return "writer_lesson" if (sub and sub.get("kind") == "lesson") else "writer_activity"
