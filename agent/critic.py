"""Deterministic quality rubric for authored BlockNote lessons.

This node does NOT call an LLM. It runs cheap deterministic checks on
the block array the agent just submitted via a frontend mutation tool
(``addLesson`` / ``updateLessonContent`` / ``appendLessonContent`` /
``patchLessonBlocks``).

On failure it returns:
  - ``report``: structured dict ``{pass, issues[], stats{}}`` stored in
    ``state.critique`` and ``state.critic_reports[lesson_id]`` for
    telemetry and UI chips.
  - ``feedback``: a concrete revision instruction string injected into
    the *fresh* system prompt on the next chat_node turn via
    ``state.critic_feedback``. This replaces the old ``SystemMessage``
    injection into ``messages`` which (a) leaked into the UI and
    (b) was stripped by ``middleware.normalize_system_messages`` before
    the LLM ever saw it.

Rubric (tuneable via env):
  - Minimum block count (default 18).
  - Required H2 section headings ("Learning objectives", "Lesson",
    "Worked example", "Practice", "Summary", "Sources").
  - Forbidden placeholder tokens in any text run: "...", "…", "etc.",
    "and so on", "TODO", "<fill in>".
  - Block-type variety (>=3 distinct types).
  - Minimum practice items when the "Practice" section is present.
"""
from __future__ import annotations
import os
import re
from typing import Any

MIN_BLOCKS = int(os.getenv("CRITIC_MIN_BLOCKS", "18"))
MAX_REVISIONS = int(os.getenv("CRITIC_MAX_REVISIONS", "2"))

REQUIRED_H2 = [
    "learning objectives",
    "lesson",
    "worked example",
    "practice",
    "summary",
    "sources",
]
FORBIDDEN_PATTERNS = [
    r"\.\.\.",
    r"…",
    r"\betc\.",
    r"\band so on\b",
    r"\bTODO\b",
    r"<\s*fill[\s_-]*in\s*>",
]
_FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_PATTERNS), re.IGNORECASE)


def _flatten_text(block: dict[str, Any]) -> str:
    parts: list[str] = []
    content = block.get("content")
    if isinstance(content, list):
        for run in content:
            if isinstance(run, dict) and run.get("type") == "text":
                parts.append(str(run.get("text", "")))
    for child in block.get("children", []) or []:
        if isinstance(child, dict):
            parts.append(_flatten_text(child))
    return " ".join(p for p in parts if p)


def _h2_titles(blocks: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "heading" and (b.get("props") or {}).get("level") == 2:
            out.append(_flatten_text(b).strip().lower())
    return out


def evaluate_lesson(blocks: Any) -> dict[str, Any]:
    """Return ``{"pass": bool, "issues": [...], "stats": {...}}``."""
    issues: list[str] = []
    if not isinstance(blocks, list) or not blocks:
        return {"pass": False, "issues": ["Lesson content is empty or not a block array."], "stats": {}}

    block_count = len(blocks)
    if block_count < MIN_BLOCKS:
        issues.append(
            f"Lesson has only {block_count} blocks (minimum {MIN_BLOCKS}). "
            f"Expand content with worked examples, more practice items, and richer explanations."
        )

    types_seen = {b.get("type") for b in blocks if isinstance(b, dict)}
    if len(types_seen) < 3:
        issues.append(
            f"Only {len(types_seen)} block type(s) used. Vary structure — add headings, "
            f"bullet/numbered lists, at least one worked example paragraph."
        )

    h2s = _h2_titles(blocks)
    missing = [req for req in REQUIRED_H2 if not any(req in h for h in h2s)]
    if missing:
        issues.append(
            "Missing required H2 sections: " + ", ".join(f'"{m.title()}"' for m in missing)
            + ". Add each as a level-2 heading in the canonical lesson skeleton."
        )

    full_text = " \n ".join(_flatten_text(b) for b in blocks if isinstance(b, dict))
    banned = set(m.group(0) for m in _FORBIDDEN_RE.finditer(full_text))
    if banned:
        issues.append(
            "Forbidden placeholder tokens found: " + ", ".join(sorted(banned))
            + '. Enumerate EVERY item — no ellipses, no "etc.", no "and so on".'
        )

    has_practice = any("practice" in h for h in h2s)
    if has_practice:
        practice_list_items = 0
        in_practice = False
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "heading" and (b.get("props") or {}).get("level") == 2:
                in_practice = "practice" in _flatten_text(b).strip().lower()
                continue
            if in_practice and b.get("type") in ("numberedListItem", "bulletListItem", "checkListItem"):
                practice_list_items += 1
        if practice_list_items < 5:
            issues.append(
                f'"Practice" section has only {practice_list_items} exercises '
                f"(minimum 5). Add more exercises followed by an Answers list."
            )

    stats = {
        "block_count": block_count,
        "distinct_types": sorted(t for t in types_seen if t),
        "h2_sections": h2s,
    }
    return {"pass": not issues, "issues": issues, "stats": stats}


def structured_critique(lesson_id: str, report: dict[str, Any], *, tool: str | None = None,
                        title: str | None = None) -> dict[str, Any]:
    """Build the structured dict stored in ``state.critique``.

    Kept as a pure helper so tests and UI chips can reuse the shape.
    """
    return {
        "lesson_id": lesson_id,
        "tool": tool,
        "title": title,
        "pass": bool(report.get("pass")),
        "issues": list(report.get("issues") or []),
        "stats": dict(report.get("stats") or {}),
    }


def format_feedback(lesson_key: str, report: dict[str, Any]) -> str:
    """Plain-text revision instructions. Injected into the NEXT system prompt
    via ``state.critic_feedback`` — NOT into ``state.messages`` (which would
    leak into the chat UI and be stripped by ``normalize_system_messages``).
    """
    if report.get("pass"):
        return f"Quality check PASSED for lesson {lesson_key}."
    bullets = "\n".join(f"  - {iss}" for iss in report.get("issues", []))
    return (
        f"QUALITY REVIEW FAILED for lesson {lesson_key}. "
        f"You MUST revise it before moving on.\n"
        f"Concrete issues found by the automated critic:\n{bullets}\n\n"
        "Next step: call readLessonBlocks to read the current state, then use "
        "patchLessonBlocks (op='replace' or 'insert') to add the missing sections "
        "and expand short ones. Do NOT rewrite the whole lesson; patch surgically."
    )


def format_exhausted(lesson_key: str, report: dict[str, Any]) -> str:
    """User-facing message when MAX_REVISIONS is exceeded. Published ONCE
    to ``state.messages`` (UI-visible) so the user knows why the loop
    stopped and can decide whether to promote as-is.
    """
    bullets = "\n".join(f"  • {iss}" for iss in report.get("issues", []))
    return (
        f"I hit my self-revision limit ({MAX_REVISIONS} passes) on lesson "
        f"**{lesson_key}** and the automated quality checks still flag:\n\n"
        f"{bullets}\n\n"
        "Let me know if you want me to keep iterating, promote the draft as-is, "
        "or focus on a specific gap."
    )
