"""In-memory draft storage for curriculum authoring.

Used by the "draft_*" MCP tools so an agent can assemble a full syllabus
without touching Supabase. Keyed by `thread_id` so each chat thread gets
an isolated drafting scratchpad; entries expire when the process exits.

Draft rows mirror the Supabase schema (syllabi/chapters/lessons) just
enough for the writer and supervisor to iterate. A separate
`promote_draft(thread_id)` helper can later copy a draft to Supabase if
the user approves.
"""
from __future__ import annotations
import threading
import time
import uuid
from typing import Any, Optional

_lock = threading.RLock()
_store: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _thread(thread_id: str) -> dict[str, Any]:
    bucket = _store.get(thread_id)
    if bucket is None:
        bucket = {
            "thread_id": thread_id,
            "syllabus": None,
            "chapters": {},  # chapter_id -> chapter dict (includes "lessons" dict)
            "chapter_order": [],
            "lessons": {},   # lesson_id -> lesson dict (global index)
            "activities": {},  # activity_id -> activity dict (global index)
        }
        _store[thread_id] = bucket
    return bucket


def reset(thread_id: Optional[str] = None) -> None:
    with _lock:
        if thread_id is None:
            _store.clear()
        else:
            _store.pop(thread_id, None)


def get_or_create_syllabus(thread_id: str, title: Optional[str] = None) -> dict:
    with _lock:
        b = _thread(thread_id)
        if b["syllabus"] is None:
            b["syllabus"] = {
                "id": f"draft-syl-{uuid.uuid4().hex[:8]}",
                "thread_id": thread_id,
                "title": title or "Untitled draft syllabus",
                "draft": True,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        return dict(b["syllabus"])


def outline(syllabus_id: str) -> dict:
    with _lock:
        for b in _store.values():
            syl = b.get("syllabus")
            if syl and syl["id"] == syllabus_id:
                chapters_out = []
                for cid in b["chapter_order"]:
                    ch = b["chapters"].get(cid)
                    if not ch:
                        continue
                    chapters_out.append({
                        **ch,
                        "lessons": [
                            {
                                "id": lid,
                                "position": b["lessons"][lid].get("position"),
                                "title": b["lessons"][lid].get("title"),
                                "block_count": len(b["lessons"][lid].get("blocks") or []),
                                "version": b["lessons"][lid].get("version", 1),
                                "updated_at": b["lessons"][lid].get("updated_at"),
                            }
                            for lid in ch.get("lesson_order", [])
                            if lid in b["lessons"]
                        ],
                        "activities": [
                            {
                                "id": aid,
                                "kind": b["activities"][aid].get("kind"),
                                "title": b["activities"][aid].get("title"),
                                "position": b["activities"][aid].get("position"),
                                "question_count": len(
                                    (b["activities"][aid].get("payload") or {}).get("questions") or []
                                ),
                                "updated_at": b["activities"][aid].get("updated_at"),
                            }
                            for aid in ch.get("activity_order", [])
                            if aid in b["activities"]
                        ],
                    })
                return {**syl, "chapters": chapters_out}
        raise ValueError(f"draft syllabus {syllabus_id} not found")


def _find_bucket_by_syllabus(syllabus_id: str) -> dict[str, Any]:
    for b in _store.values():
        if b.get("syllabus") and b["syllabus"]["id"] == syllabus_id:
            return b
    raise ValueError(f"draft syllabus {syllabus_id} not found")


def _find_bucket_by_chapter(chapter_id: str) -> dict[str, Any]:
    for b in _store.values():
        if chapter_id in b["chapters"]:
            return b
    raise ValueError(f"draft chapter {chapter_id} not found")


def _find_bucket_by_lesson(lesson_id: str) -> dict[str, Any]:
    for b in _store.values():
        if lesson_id in b["lessons"]:
            return b
    raise ValueError(f"draft lesson {lesson_id} not found")


def list_chapters(syllabus_id: str) -> list[dict]:
    with _lock:
        b = _find_bucket_by_syllabus(syllabus_id)
        return [dict(b["chapters"][c]) for c in b["chapter_order"] if c in b["chapters"]]


def add_chapter(syllabus_id: str, title: str, summary: Optional[str] = None,
                position: Optional[int] = None) -> dict:
    with _lock:
        b = _find_bucket_by_syllabus(syllabus_id)
        cid = f"draft-ch-{uuid.uuid4().hex[:8]}"
        if position is None:
            position = len(b["chapter_order"])
        ch = {
            "id": cid,
            "syllabus_id": syllabus_id,
            "title": title,
            "summary": summary,
            "position": position,
            "lesson_order": [],
            "activity_order": [],
            "draft": True,
            "created_at": _now_iso(),
        }
        b["chapters"][cid] = ch
        b["chapter_order"].insert(min(position, len(b["chapter_order"])), cid)
        return dict(ch)


def list_lessons(chapter_id: str) -> list[dict]:
    with _lock:
        b = _find_bucket_by_chapter(chapter_id)
        ch = b["chapters"][chapter_id]
        return [dict(b["lessons"][lid]) for lid in ch["lesson_order"] if lid in b["lessons"]]


def read_lesson_blocks(lesson_id: str) -> dict:
    with _lock:
        b = _find_bucket_by_lesson(lesson_id)
        l = b["lessons"][lesson_id]
        return {"id": l["id"], "title": l["title"], "blocks": list(l.get("blocks") or []),
                "version": l.get("version", 1)}


def add_lesson(chapter_id: str, title: str, blocks: Optional[list[dict]] = None,
               position: Optional[int] = None, author: Optional[str] = None) -> dict:
    with _lock:
        b = _find_bucket_by_chapter(chapter_id)
        ch = b["chapters"][chapter_id]
        lid = f"draft-les-{uuid.uuid4().hex[:8]}"
        if position is None:
            position = len(ch["lesson_order"])
        lesson = {
            "id": lid,
            "chapter_id": chapter_id,
            "title": title,
            "blocks": list(blocks or []),
            "position": position,
            "version": 1,
            "last_author": author,
            "draft": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        b["lessons"][lid] = lesson
        ch["lesson_order"].insert(min(position, len(ch["lesson_order"])), lid)
        return dict(lesson)


def _bump(lesson: dict) -> None:
    lesson["version"] = int(lesson.get("version", 1)) + 1
    lesson["updated_at"] = _now_iso()


def update_lesson_content(lesson_id: str, blocks: list[dict],
                          expected_version: Optional[int] = None,
                          author: Optional[str] = None) -> dict:
    with _lock:
        b = _find_bucket_by_lesson(lesson_id)
        lesson = b["lessons"][lesson_id]
        if expected_version is not None and lesson.get("version", 1) != expected_version:
            raise ValueError(
                f"draft version conflict: expected {expected_version}, actual {lesson.get('version', 1)}"
            )
        lesson["blocks"] = list(blocks)
        lesson["last_author"] = author
        _bump(lesson)
        return dict(lesson)


def append_lesson_content(lesson_id: str, blocks: list[dict],
                          author: Optional[str] = None) -> dict:
    with _lock:
        b = _find_bucket_by_lesson(lesson_id)
        lesson = b["lessons"][lesson_id]
        lesson["blocks"] = list(lesson.get("blocks") or []) + list(blocks)
        lesson["last_author"] = author
        _bump(lesson)
        return dict(lesson)


def patch_lesson_blocks(lesson_id: str, patches: list[dict],
                        author: Optional[str] = None) -> dict:
    with _lock:
        b = _find_bucket_by_lesson(lesson_id)
        lesson = b["lessons"][lesson_id]
        blocks = list(lesson.get("blocks") or [])
        for raw in patches:
            op = raw.get("op")
            block_id = raw.get("block_id")
            block = raw.get("block")
            idx = next((i for i, bl in enumerate(blocks) if bl.get("id") == block_id), -1)
            if idx < 0 and op not in ("insert_after", "insert_before"):
                raise ValueError(f"draft block {block_id} not found")
            if op == "replace":
                blocks[idx] = block or blocks[idx]
            elif op == "delete":
                blocks.pop(idx)
            elif op == "insert_after":
                if not block:
                    raise ValueError("insert_after requires 'block'")
                blocks.insert(idx + 1 if idx >= 0 else len(blocks), block)
            elif op == "insert_before":
                if not block:
                    raise ValueError("insert_before requires 'block'")
                blocks.insert(idx if idx >= 0 else 0, block)
            else:
                raise ValueError(f"unknown patch op: {op}")
        lesson["blocks"] = blocks
        lesson["last_author"] = author
        _bump(lesson)
        return dict(lesson)


def snapshot(thread_id: str) -> dict:
    """Return a JSON-serializable dump of the full draft for a thread.

    Useful for a future `promote_draft` tool that copies the draft into
    Supabase, or for clients that want to preview the drafted syllabus.
    """
    with _lock:
        b = _store.get(thread_id)
        if b is None:
            return {"thread_id": thread_id, "syllabus": None, "chapters": []}
        syl = b.get("syllabus")
        chapters = []
        for cid in b["chapter_order"]:
            ch = b["chapters"].get(cid)
            if not ch:
                continue
            chapters.append({
                **ch,
                "lessons": [dict(b["lessons"][lid]) for lid in ch["lesson_order"] if lid in b["lessons"]],
                "activities": [
                    dict(b["activities"][aid])
                    for aid in ch.get("activity_order", [])
                    if aid in b["activities"]
                ],
            })
        return {"thread_id": thread_id, "syllabus": dict(syl) if syl else None, "chapters": chapters}


# ---------- activities (quizzes, etc.) ----------

_ALLOWED_ACTIVITY_KINDS = {"quiz"}


def _validate_quiz_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("quiz payload must be an object")
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("quiz payload.questions must be a non-empty list")
    seen_qids: set[str] = set()
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise ValueError(f"question #{i} must be an object")
        qid = q.get("id")
        if not isinstance(qid, str) or not qid:
            raise ValueError(f"question #{i} missing string 'id'")
        if qid in seen_qids:
            raise ValueError(f"duplicate question id '{qid}'")
        seen_qids.add(qid)
        if not isinstance(q.get("prompt"), str) or not q["prompt"].strip():
            raise ValueError(f"question '{qid}' missing 'prompt'")
        choices = q.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise ValueError(f"question '{qid}' needs at least 2 choices")
        choice_ids: set[str] = set()
        for c in choices:
            if not isinstance(c, dict):
                raise ValueError(f"question '{qid}' has a non-object choice")
            cid = c.get("id")
            if not isinstance(cid, str) or not cid:
                raise ValueError(f"question '{qid}' choice missing 'id'")
            if cid in choice_ids:
                raise ValueError(f"question '{qid}' has duplicate choice id '{cid}'")
            choice_ids.add(cid)
            if not isinstance(c.get("text"), str) or not c["text"].strip():
                raise ValueError(f"question '{qid}' choice '{cid}' missing 'text'")
        correct = q.get("correct_choice_ids")
        if not isinstance(correct, list) or not correct:
            raise ValueError(f"question '{qid}' missing 'correct_choice_ids'")
        for cid in correct:
            if cid not in choice_ids:
                raise ValueError(
                    f"question '{qid}' correct id '{cid}' is not among its choices"
                )
        kind = q.get("kind") or "single"
        if kind not in {"single", "multi", "true_false"}:
            raise ValueError(f"question '{qid}' has unknown kind '{kind}'")
        if kind in {"single", "true_false"} and len(correct) != 1:
            raise ValueError(
                f"question '{qid}' kind={kind} must have exactly one correct choice"
            )


def add_activity(chapter_id: str, kind: str, title: str, payload: dict,
                 position: Optional[int] = None, author: Optional[str] = None) -> dict:
    if kind not in _ALLOWED_ACTIVITY_KINDS:
        raise ValueError(f"unsupported activity kind: {kind}")
    if kind == "quiz":
        _validate_quiz_payload(payload)
    with _lock:
        b = _find_bucket_by_chapter(chapter_id)
        ch = b["chapters"][chapter_id]
        ch.setdefault("activity_order", [])
        aid = f"draft-act-{uuid.uuid4().hex[:8]}"
        if position is None:
            position = len(ch["activity_order"])
        activity = {
            "id": aid,
            "chapter_id": chapter_id,
            "kind": kind,
            "title": title,
            "payload": payload,
            "position": position,
            "last_author": author,
            "draft": True,
            "version": 1,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        b["activities"][aid] = activity
        ch["activity_order"].insert(min(position, len(ch["activity_order"])), aid)
        return dict(activity)


def list_activities(chapter_id: str) -> list[dict]:
    with _lock:
        b = _find_bucket_by_chapter(chapter_id)
        ch = b["chapters"][chapter_id]
        return [
            dict(b["activities"][aid])
            for aid in ch.get("activity_order", [])
            if aid in b["activities"]
        ]


def get_activity(activity_id: str) -> dict:
    with _lock:
        for b in _store.values():
            if activity_id in b.get("activities", {}):
                return dict(b["activities"][activity_id])
        raise ValueError(f"draft activity {activity_id} not found")


def update_activity_payload(activity_id: str, payload: dict,
                            author: Optional[str] = None) -> dict:
    with _lock:
        for b in _store.values():
            if activity_id in b.get("activities", {}):
                act = b["activities"][activity_id]
                if act.get("kind") == "quiz":
                    _validate_quiz_payload(payload)
                act["payload"] = payload
                act["last_author"] = author
                act["version"] = int(act.get("version", 1)) + 1
                act["updated_at"] = _now_iso()
                return dict(act)
        raise ValueError(f"draft activity {activity_id} not found")
