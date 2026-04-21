"""Unit tests for activity payload validation.

These run against the pure-Python `_validate_payload` function (no DB).
Live integration coverage is done separately against the dev Supabase project
via PostgREST in the release smoke script.
"""
from __future__ import annotations
import importlib

import pytest


@pytest.fixture(scope="module")
def va():
    mod = importlib.import_module("curriculum_mcp.tools_activities")
    return mod


def test_activity_kinds_frozen(va):
    assert va.ACTIVITY_KINDS == ("mcq_quiz", "drill_exercises", "flashcards", "project")


def test_import_registers_symbols(va):
    for sym in ("register_activities", "_validate_payload", "ACTIVITY_KINDS"):
        assert hasattr(va, sym)


@pytest.mark.parametrize(
    "kind,payload,expected_code",
    [
        ("mcq_quiz", {"questions": []}, "invalid_payload"),
        ("mcq_quiz", {"questions": [{"prompt": "x", "choices": ["a"], "correct_index": 0}]}, "invalid_payload"),
        ("mcq_quiz", {"questions": [{"prompt": "x", "choices": ["a", "b"], "correct_index": 7}]}, "invalid_payload"),
        ("mcq_quiz", {"questions": [{"prompt": "", "choices": ["a", "b"], "correct_index": 0}]}, "invalid_payload"),
        ("drill_exercises", {"problems": [{"prompt": "p"}]}, "invalid_payload"),
        ("drill_exercises", {"problems": []}, "invalid_payload"),
        ("flashcards", {"cards": [{"front": "f"}]}, "invalid_payload"),
        ("flashcards", {"cards": []}, "invalid_payload"),
        ("project", {"brief": "b", "deliverables": []}, "invalid_payload"),
        ("project", {"brief": "", "deliverables": ["x"]}, "invalid_payload"),
        ("project", {"brief": "b", "deliverables": ["x"], "rubric": [{"criterion": "c", "weight": "bad"}]}, "invalid_payload"),
        ("weirdkind", {}, "invalid_kind"),
        ("mcq_quiz", "not-a-dict", "invalid_payload"),
    ],
)
def test_invalid_payloads_return_error(va, kind, payload, expected_code):
    res = va._validate_payload(kind, payload)
    assert res is not None
    assert res["ok"] is False
    assert res["error"]["code"] == expected_code


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("mcq_quiz", {"questions": [{"prompt": "2+2", "choices": ["3", "4"], "correct_index": 1}]}),
        ("mcq_quiz", {"questions": [{"prompt": "2+2", "choices": ["3", "4"], "correct_index": 1, "explanation": "math"}]}),
        ("drill_exercises", {"problems": [{"prompt": "x+1=2", "answer": "1"}]}),
        ("drill_exercises", {"problems": [{"prompt": "x+1=2", "answer": "1", "hints": ["subtract"]}]}),
        ("flashcards", {"cards": [{"front": "HTTP", "back": "HyperText Transfer Protocol"}]}),
        ("project", {"brief": "Build x", "deliverables": ["repo"]}),
        ("project", {"brief": "Build x", "deliverables": ["repo"], "rubric": [{"criterion": "quality", "weight": 0.5}]}),
    ],
)
def test_valid_payloads_pass(va, kind, payload):
    assert va._validate_payload(kind, payload) is None
