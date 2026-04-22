"""LLM-based critic with structured pass/fail + deterministic guards."""
from __future__ import annotations
import logging
from typing import Any

from agent.llm import get_llm
from agent_v2.schemas import CriticSchema
from agent_v2.state import AgentStateV2

logger = logging.getLogger(__name__)


def _deterministic_checks(draft: dict) -> list[str]:
    issues: list[str] = []
    if draft.get("kind") == "lesson":
        blocks = draft.get("blocks") or []
        if len(blocks) < 10:
            issues.append(f"Only {len(blocks)} blocks (minimum 10).")
        types = {b.get("type") for b in blocks if isinstance(b, dict)}
        if len(types) < 3:
            issues.append("Too few block types — add headings/lists/paragraphs.")
        text = " ".join(
            str(r.get("text", ""))
            for b in blocks if isinstance(b, dict)
            for r in (b.get("content") or []) if isinstance(r, dict)
        ).lower()
        for bad in ["todo", "...", "…", "etc.", "and so on"]:
            if bad in text:
                issues.append(f"Forbidden placeholder token: {bad!r}.")
                break
    elif draft.get("kind") == "activity":
        opts = draft.get("options") or []
        if len(opts) < 2:
            issues.append("Activity must have at least 2 options.")
        ci = draft.get("correct_index")
        if draft.get("multi"):
            if not isinstance(ci, list) or not ci:
                issues.append("multi=True requires correct_index as non-empty list.")
        else:
            if not isinstance(ci, int) or ci < 0 or ci >= len(opts):
                issues.append("correct_index is out of range for single-choice activity.")
    return issues


async def critic_node(state: AgentStateV2) -> dict[str, Any]:
    draft = state.get("current_draft") or {}
    plan = state.get("plan") or {}
    ci = state.get("current_chapter_idx", 0)
    si = state.get("current_substep_idx", 0)
    sub = ((plan.get("chapters") or [{}])[ci].get("substeps") or [{}])[si] if plan.get("chapters") else {}
    goals = sub.get("goals") or []

    det = _deterministic_checks(draft)
    if det:
        return {"current_critic": {"pass_": False, "issues": det, "score": 0.0}}

    llm = get_llm().with_structured_output(CriticSchema)
    prompt = f"""You are a strict content reviewer. Decide PASS/FAIL for the draft below
against every goal. Passing requires EVERY goal met concretely (not just mentioned).

SubStep: {sub.get("title")!r}  (kind={sub.get("kind")})
Goals:
{chr(10).join("- " + g for g in goals)}

Draft JSON:
{draft}

Return CriticSchema. If any goal is not clearly covered, set passed=false and list the
gap in `issues` as a concrete imperative (e.g. 'Add a worked example for pointer arithmetic')."""
    try:
        report: CriticSchema = await llm.ainvoke(prompt)
        return {"current_critic": {"pass_": bool(report.passed), "issues": list(report.issues), "score": float(report.score or 0.0)}}
    except Exception as exc:
        logger.exception("critic LLM failed: %s", exc)
        return {"current_critic": {"pass_": False, "issues": [f"critic error: {exc}"], "score": 0.0}}
