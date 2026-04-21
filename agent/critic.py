"""Deterministic quality rubric for authored BlockNote lessons.

This node does NOT call an LLM. It runs a set of cheap, deterministic
checks against the block array the agent just submitted via a frontend
mutation tool (addLesson / updateLessonContent / appendLessonContent /
patchLessonBlocks). On failure it returns a structured list of concrete
fix instructions that chat_node injects as a SystemMessage, which is
observably more reliable than hoping the prompt alone is enforced.

Rubric (tuneable via env):
  - Minimum block count (default 18).
  - Required H2 section headings ("Learning objectives", "Lesson",
    "Worked example", "Practice", "Summary", "Sources").
  - Forbidden placeholder tokens in any text run: "...", "…", "etc.",
    "and so on", "TODO", "<fill in>".
  - Block-type variety (>=3 distinct types).
  - Minimum number of practice items when the "Practice" section is
    present (>= 5 numbered/bullet list items in a trailing run).
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

CANNED_HOOK_PATTERNS = [
    r"^\s*in this (course|lesson|chapter)[^.]{0,80}you will learn",
    r"^\s*by the end of this (course|lesson|chapter)[^.]{0,80}you will",
    r"^\s*welcome to this (course|lesson|chapter)",
    r"^\s*this (course|lesson|chapter) (is|will be) about",
]
_CANNED_HOOK_RE = re.compile("|".join(CANNED_HOOK_PATTERNS), re.IGNORECASE)
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
    """Return {"pass": bool, "issues": [str, ...], "stats": {...}}."""
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
            + '. The hard rule is: enumerate EVERY item in any sequence — no ellipses, no "etc.", no "and so on".'
        )


    first_para = next(
        (b for b in blocks
         if isinstance(b, dict) and b.get("type") == "paragraph"
         and _flatten_text(b).strip()),
        None,
    )
    if first_para is not None:
        opener = _flatten_text(first_para).strip()
        if _CANNED_HOOK_RE.search(opener):
            issues.append(
                'Opening hook is a canned boilerplate ("In this course you will learn..." / '
                '"By the end of this lesson you will..." / "Welcome to..."). '
                "Rewrite it as an ADAPTIVE opener drawn from the lesson's real source "
                "material: a concrete fact, a question, an example, a short anecdote, "
                "or a surprising number."
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


def format_feedback(lesson_key: str, report: dict[str, Any]) -> str:
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
