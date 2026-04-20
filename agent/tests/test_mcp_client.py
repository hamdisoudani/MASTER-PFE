"""Smoke tests for agent.mcp_client — no live server required."""
from __future__ import annotations
import os

from agent.mcp_client import (
    CURRICULUM_TOOL_NAMES,
    _aload_curriculum_tools,
    load_curriculum_tools,
)


def test_curriculum_tool_names_cover_expected():
    expected = {
        "addChapter",
        "addLesson",
        "updateLessonContent",
        "appendLessonContent",
        "patchLessonBlocks",
        "readLessonBlocks",
        "getOrCreateSyllabus",
        "getSyllabusOutline",
        "listChapters",
        "listLessons",
    }
    assert expected.issubset(CURRICULUM_TOOL_NAMES)


def test_load_returns_empty_without_env(monkeypatch):
    monkeypatch.delenv("CURRICULUM_MCP_URL", raising=False)
    assert load_curriculum_tools() == []


def test_load_returns_empty_on_unreachable(monkeypatch):
    monkeypatch.setenv("CURRICULUM_MCP_URL", "http://127.0.0.1:1/mcp")
    # Even if the adapter package isn't installed, or the port is closed,
    # the helper must not raise.
    tools = load_curriculum_tools()
    assert isinstance(tools, list)
