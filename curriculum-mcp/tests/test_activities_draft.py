"""Regression tests for draft chapter activities (quiz)."""
from __future__ import annotations
import pytest

from curriculum_mcp import draft_store


@pytest.fixture(autouse=True)
def _clean():
    draft_store.reset()
    yield
    draft_store.reset()


def _quiz_payload():
    return {
        "instructions": "Pick the best answer.",
        "questions": [
            {
                "id": "q1",
                "prompt": "2+2 ?",
                "kind": "single",
                "choices": [
                    {"id": "a", "text": "3"},
                    {"id": "b", "text": "4"},
                    {"id": "c", "text": "5"},
                ],
                "correct_choice_ids": ["b"],
                "explanation": "Basic arithmetic.",
            },
            {
                "id": "q2",
                "prompt": "Primes?",
                "kind": "multi",
                "choices": [
                    {"id": "a", "text": "2"},
                    {"id": "b", "text": "3"},
                    {"id": "c", "text": "4"},
                    {"id": "d", "text": "9"},
                ],
                "correct_choice_ids": ["a", "b"],
            },
        ],
    }


def test_add_activity_attaches_to_chapter_and_shows_in_outline():
    syl = draft_store.get_or_create_syllabus("t1", "Math")
    ch = draft_store.add_chapter(syl["id"], "Numbers")
    act = draft_store.add_activity(ch["id"], "quiz", "Chapter 1 quiz", _quiz_payload())
    assert act["id"].startswith("draft-act-")
    assert act["kind"] == "quiz"
    assert act["payload"]["questions"][0]["correct_choice_ids"] == ["b"]

    outline = draft_store.outline(syl["id"])
    ch0 = outline["chapters"][0]
    assert len(ch0["activities"]) == 1
    assert ch0["activities"][0]["kind"] == "quiz"
    assert ch0["activities"][0]["question_count"] == 2

    snap = draft_store.snapshot("t1")
    assert snap["chapters"][0]["activities"][0]["payload"]["questions"][1]["kind"] == "multi"


def test_invalid_correct_id_rejected():
    syl = draft_store.get_or_create_syllabus("t2", "X")
    ch = draft_store.add_chapter(syl["id"], "Ch")
    bad = _quiz_payload()
    bad["questions"][0]["correct_choice_ids"] = ["zzz"]
    with pytest.raises(ValueError):
        draft_store.add_activity(ch["id"], "quiz", "Bad", bad)


def test_single_kind_requires_exactly_one_correct():
    syl = draft_store.get_or_create_syllabus("t3", "X")
    ch = draft_store.add_chapter(syl["id"], "Ch")
    p = _quiz_payload()
    p["questions"][0]["correct_choice_ids"] = ["a", "b"]
    with pytest.raises(ValueError):
        draft_store.add_activity(ch["id"], "quiz", "Bad", p)


def test_unknown_kind_rejected():
    syl = draft_store.get_or_create_syllabus("t4", "X")
    ch = draft_store.add_chapter(syl["id"], "Ch")
    with pytest.raises(ValueError):
        draft_store.add_activity(ch["id"], "essay", "Bad", _quiz_payload())


def test_update_activity_payload_bumps_version():
    syl = draft_store.get_or_create_syllabus("t5", "X")
    ch = draft_store.add_chapter(syl["id"], "Ch")
    act = draft_store.add_activity(ch["id"], "quiz", "Q", _quiz_payload())
    assert act["version"] == 1
    new_payload = _quiz_payload()
    new_payload["instructions"] = "Try again."
    updated = draft_store.update_activity_payload(act["id"], new_payload)
    assert updated["version"] == 2
    assert updated["payload"]["instructions"] == "Try again."
