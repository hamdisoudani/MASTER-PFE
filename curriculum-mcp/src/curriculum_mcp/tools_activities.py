"""Activity MCP tools.

Activities are practice/assessment units attached to a chapter. Each activity
has a ``kind`` that determines the shape of its ``payload``. The MCP layer
validates the payload per kind so the frontend (player components) can render
without defensive fallbacks everywhere.

Supported kinds
---------------
- ``mcq_quiz``         -> {"questions": [{prompt, choices[>=2], correct_index, explanation?}, ...]}
- ``drill_exercises``  -> {"problems":  [{prompt, answer, hints?[]}, ...]}
- ``flashcards``       -> {"cards":     [{front, back}, ...]}
- ``project``          -> {"brief", "deliverables"[>=1], "rubric"?[{criterion, weight?}]}

All tools return the same ``{ok,error}`` envelope used elsewhere in the MCP
server, so subagents can reason about failures without crashing the session.
"""
from __future__ import annotations
import logging
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP

from .db import client

logger = logging.getLogger(__name__)

ACTIVITY_KINDS = ("mcq_quiz", "drill_exercises", "flashcards", "project")


# ---------- envelope (duplicated to avoid circular import) ------------------

def _ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def _err(code: str, message: str, hint: Optional[str] = None) -> dict:
    env: dict = {"ok": False, "error": {"code": code, "message": message}}
    if hint:
        env["error"]["hint"] = hint
    return env


def _is_uuid(value: Any) -> bool:
    import uuid
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
            hint=f"Call listActivities/getSyllabusOutline to discover a real {field}.",
        )
    return None


# ---------- payload validation ---------------------------------------------

def _validate_payload(kind: str, payload: Any) -> Optional[dict]:
    """Return an error envelope if payload is invalid for the given kind, else None."""
    if not isinstance(payload, dict):
        return _err(
            "invalid_payload",
            f"payload must be a JSON object, got {type(payload).__name__}.",
            hint=f"For kind={kind!r} pass the matching object shape.",
        )

    if kind == "mcq_quiz":
        qs = payload.get("questions")
        if not isinstance(qs, list) or not qs:
            return _err("invalid_payload", "mcq_quiz.payload.questions must be a non-empty array.")
        for i, q in enumerate(qs):
            if not isinstance(q, dict):
                return _err("invalid_payload", f"questions[{i}] must be an object.")
            prompt = q.get("prompt")
            choices = q.get("choices")
            correct = q.get("correct_index")
            if not isinstance(prompt, str) or not prompt.strip():
                return _err("invalid_payload", f"questions[{i}].prompt must be a non-empty string.")
            if not isinstance(choices, list) or len(choices) < 2:
                return _err("invalid_payload", f"questions[{i}].choices must be an array of >=2 strings.")
            if not all(isinstance(c, str) and c.strip() for c in choices):
                return _err("invalid_payload", f"questions[{i}].choices must all be non-empty strings.")
            if not isinstance(correct, int) or not (0 <= correct < len(choices)):
                return _err(
                    "invalid_payload",
                    f"questions[{i}].correct_index must be an int in [0, {len(choices) - 1}].",
                )
            expl = q.get("explanation")
            if expl is not None and not isinstance(expl, str):
                return _err("invalid_payload", f"questions[{i}].explanation must be a string if provided.")
        return None

    if kind == "drill_exercises":
        probs = payload.get("problems")
        if not isinstance(probs, list) or not probs:
            return _err("invalid_payload", "drill_exercises.payload.problems must be a non-empty array.")
        for i, p in enumerate(probs):
            if not isinstance(p, dict):
                return _err("invalid_payload", f"problems[{i}] must be an object.")
            if not isinstance(p.get("prompt"), str) or not p["prompt"].strip():
                return _err("invalid_payload", f"problems[{i}].prompt must be a non-empty string.")
            if not isinstance(p.get("answer"), str) or not p["answer"].strip():
                return _err("invalid_payload", f"problems[{i}].answer must be a non-empty string.")
            hints = p.get("hints")
            if hints is not None:
                if not isinstance(hints, list) or not all(isinstance(h, str) for h in hints):
                    return _err("invalid_payload", f"problems[{i}].hints must be an array of strings if provided.")
        return None

    if kind == "flashcards":
        cards = payload.get("cards")
        if not isinstance(cards, list) or not cards:
            return _err("invalid_payload", "flashcards.payload.cards must be a non-empty array.")
        for i, c in enumerate(cards):
            if not isinstance(c, dict):
                return _err("invalid_payload", f"cards[{i}] must be an object.")
            if not isinstance(c.get("front"), str) or not c["front"].strip():
                return _err("invalid_payload", f"cards[{i}].front must be a non-empty string.")
            if not isinstance(c.get("back"), str) or not c["back"].strip():
                return _err("invalid_payload", f"cards[{i}].back must be a non-empty string.")
        return None

    if kind == "project":
        brief = payload.get("brief")
        delivs = payload.get("deliverables")
        if not isinstance(brief, str) or not brief.strip():
            return _err("invalid_payload", "project.payload.brief must be a non-empty string.")
        if not isinstance(delivs, list) or not delivs:
            return _err("invalid_payload", "project.payload.deliverables must be a non-empty array of strings.")
        if not all(isinstance(d, str) and d.strip() for d in delivs):
            return _err("invalid_payload", "project.payload.deliverables must all be non-empty strings.")
        rubric = payload.get("rubric")
        if rubric is not None:
            if not isinstance(rubric, list):
                return _err("invalid_payload", "project.payload.rubric must be an array if provided.")
            for i, r in enumerate(rubric):
                if not isinstance(r, dict) or not isinstance(r.get("criterion"), str) or not r["criterion"].strip():
                    return _err("invalid_payload", f"rubric[{i}].criterion must be a non-empty string.")
                w = r.get("weight")
                if w is not None and not isinstance(w, (int, float)):
                    return _err("invalid_payload", f"rubric[{i}].weight must be a number if provided.")
        return None

    return _err(
        "invalid_kind",
        f"kind must be one of {list(ACTIVITY_KINDS)}, got {kind!r}.",
    )


# ---------- registration ----------------------------------------------------

def register_activities(mcp: FastMCP) -> None:
    """Attach activity tools to the shared FastMCP instance."""

    @mcp.tool()
    def listActivities(chapter_id: str) -> dict:
        """List activities under a chapter, ordered by position. Payload is omitted
        from the list response to keep it small; call readActivity for the full payload."""
        bad = _require_uuid(chapter_id, "chapter_id")
        if bad:
            return bad
        try:
            rows = (
                client().table("activities")
                .select("id,chapter_id,position,kind,title,metadata,version,updated_at")
                .eq("chapter_id", chapter_id).order("position").execute().data
            )
            return _ok(rows)
        except Exception as e:
            logger.exception("listActivities failed")
            return _err("db_error", f"listActivities failed: {e}")

    @mcp.tool()
    def readActivity(activity_id: str) -> dict:
        """Return one full activity row including payload."""
        bad = _require_uuid(activity_id, "activity_id")
        if bad:
            return bad
        try:
            row = (
                client().table("activities").select("*")
                .eq("id", activity_id).limit(1).execute().data
            )
            if not row:
                return _err(
                    "activity_not_found",
                    f"No activity with id {activity_id}.",
                    hint="Call listActivities(chapter_id) to discover real ids.",
                )
            return _ok(row[0])
        except Exception as e:
            logger.exception("readActivity failed")
            return _err("db_error", f"readActivity failed: {e}")

    @mcp.tool()
    def addActivity(chapter_id: str, kind: str, title: str, payload: dict,
                    position: Optional[int] = None, author: Optional[str] = None,
                    metadata: Optional[dict] = None) -> dict:
        """Create an activity under an EXISTING chapter.

        ``kind`` must be one of mcq_quiz / drill_exercises / flashcards / project.
        ``payload`` is validated against the kind's schema and rejected cleanly
        (no partial row written) if malformed.
        """
        bad = _require_uuid(chapter_id, "chapter_id")
        if bad:
            return bad
        if not isinstance(title, str) or not title.strip():
            return _err("invalid_input", "title must be a non-empty string.")
        if kind not in ACTIVITY_KINDS:
            return _err("invalid_kind", f"kind must be one of {list(ACTIVITY_KINDS)}.")
        bad = _validate_payload(kind, payload)
        if bad:
            return bad
        if metadata is not None and not isinstance(metadata, dict):
            return _err("invalid_input", "metadata must be a JSON object if provided.")
        try:
            sb = client()
            chap = (
                sb.table("chapters").select("id").eq("id", chapter_id).limit(1).execute().data
            )
            if not chap:
                return _err(
                    "chapter_not_found",
                    f"Cannot add activity: chapter {chapter_id} does not exist.",
                    hint="Call getSyllabusOutline(syllabus_id) first; never invent chapter_ids.",
                )
            if position is None:
                existing = (
                    sb.table("activities").select("position").eq("chapter_id", chapter_id)
                    .order("position", desc=True).limit(1).execute().data
                )
                position = (existing[0]["position"] + 1) if existing else 0
            row = sb.table("activities").insert({
                "chapter_id": chapter_id,
                "kind": kind,
                "title": title.strip(),
                "payload": payload,
                "metadata": metadata or {},
                "position": position,
                "last_author": author,
            }).execute().data[0]
            try:
                sb.table("activity_edits").insert({
                    "activity_id": row["id"], "op": "add",
                    "patch": {"kind": kind, "title": title, "payload": payload},
                    "to_version": row["version"], "author": author,
                }).execute()
            except Exception:
                logger.exception("addActivity: audit insert failed (non-fatal)")
            return _ok(row)
        except Exception as e:
            logger.exception("addActivity failed")
            return _err("db_error", f"addActivity failed: {e}")

    @mcp.tool()
    def patchActivity(activity_id: str,
                      title: Optional[str] = None,
                      payload: Optional[dict] = None,
                      metadata: Optional[dict] = None,
                      expected_version: Optional[int] = None,
                      author: Optional[str] = None) -> dict:
        """Partial update. At least one of title/payload/metadata must be provided.
        If ``payload`` is provided it is re-validated against the row's existing kind."""
        bad = _require_uuid(activity_id, "activity_id")
        if bad:
            return bad
        if title is None and payload is None and metadata is None:
            return _err("invalid_input", "Provide at least one of title/payload/metadata.")
        if title is not None and (not isinstance(title, str) or not title.strip()):
            return _err("invalid_input", "title must be a non-empty string if provided.")
        if metadata is not None and not isinstance(metadata, dict):
            return _err("invalid_input", "metadata must be a JSON object if provided.")
        try:
            sb = client()
            cur = (
                sb.table("activities").select("kind,version")
                .eq("id", activity_id).limit(1).execute().data
            )
            if not cur:
                return _err(
                    "activity_not_found",
                    f"Cannot patch: activity {activity_id} does not exist.",
                )
            current = cur[0]
            if expected_version is not None and current["version"] != expected_version:
                return _err(
                    "version_conflict",
                    f"version conflict: expected {expected_version}, actual {current['version']}.",
                    hint="Re-read via readActivity and retry with the fresh version.",
                )
            if payload is not None:
                bad = _validate_payload(current["kind"], payload)
                if bad:
                    return bad
            updates: dict = {"last_author": author}
            if title is not None:
                updates["title"] = title.strip()
            if payload is not None:
                updates["payload"] = payload
            if metadata is not None:
                updates["metadata"] = metadata
            updated = (
                sb.table("activities").update(updates).eq("id", activity_id).execute().data[0]
            )
            try:
                sb.table("activity_edits").insert({
                    "activity_id": activity_id, "op": "patch",
                    "patch": {k: v for k, v in updates.items() if k != "last_author"},
                    "from_version": current["version"], "to_version": updated["version"],
                    "author": author,
                }).execute()
            except Exception:
                logger.exception("patchActivity: audit insert failed (non-fatal)")
            return _ok(updated)
        except Exception as e:
            logger.exception("patchActivity failed")
            return _err("db_error", f"patchActivity failed: {e}")

    @mcp.tool()
    def deleteActivity(activity_id: str, author: Optional[str] = None) -> dict:
        bad = _require_uuid(activity_id, "activity_id")
        if bad:
            return bad
        try:
            sb = client()
            cur = (
                sb.table("activities").select("version")
                .eq("id", activity_id).limit(1).execute().data
            )
            if not cur:
                return _err(
                    "activity_not_found",
                    f"Cannot delete: activity {activity_id} does not exist.",
                )
            try:
                sb.table("activity_edits").insert({
                    "activity_id": activity_id, "op": "delete",
                    "from_version": cur[0]["version"], "to_version": cur[0]["version"],
                    "author": author,
                }).execute()
            except Exception:
                logger.exception("deleteActivity: audit insert failed (non-fatal)")
            sb.table("activities").delete().eq("id", activity_id).execute()
            return _ok({"id": activity_id, "deleted": True})
        except Exception as e:
            logger.exception("deleteActivity failed")
            return _err("db_error", f"deleteActivity failed: {e}")
