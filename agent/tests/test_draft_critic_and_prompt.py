"""Tests for the new draft-path critic hook, frontend-shadow filter,
and state-conditional system prompt.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent import nodes
from agent.prompts import build_system_prompt


# ---------------------------------------------------------------------------
# tools_post_hook — draft-critic bridge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_post_hook_populates_last_authored_lesson_for_draft_add():
    tc = {
        "id": "call_1",
        "name": "draftAddLesson",
        "args": {
            "chapter_id": "chap-1",
            "title": "Counting to 10",
            "blocks": [{"type": "paragraph", "props": {}, "content": [], "children": []}],
        },
    }
    ai = AIMessage(content="", tool_calls=[tc])
    tm = ToolMessage(content='{"id":"les-42","version":1}', tool_call_id="call_1")
    state = {"messages": [HumanMessage(content="make a lesson"), ai, tm]}
    out = await nodes.tools_post_hook(state, {})
    assert "last_authored_lesson" in out
    la = out["last_authored_lesson"]
    assert la["tool"] == "draftAddLesson"
    assert la["lesson_id"] == "chap-1"
    assert la["title"] == "Counting to 10"
    assert isinstance(la["blocks"], list) and len(la["blocks"]) == 1


@pytest.mark.asyncio
async def test_tools_post_hook_ignores_non_draft_tool_calls():
    tc = {"id": "call_1", "name": "web_search", "args": {"query": "math"}}
    ai = AIMessage(content="", tool_calls=[tc])
    tm = ToolMessage(content="[]", tool_call_id="call_1")
    out = await nodes.tools_post_hook({"messages": [ai, tm]}, {})
    assert out == {}


@pytest.mark.asyncio
async def test_tools_post_hook_skips_failed_tool_message():
    tc = {"id": "call_1", "name": "draftAddLesson", "args": {"blocks": []}}
    ai = AIMessage(content="", tool_calls=[tc])
    tm = ToolMessage(content='{"error":"boom","type":"RuntimeError"}', tool_call_id="call_1", status="error")
    out = await nodes.tools_post_hook({"messages": [ai, tm]}, {})
    assert out == {}


@pytest.mark.asyncio
async def test_route_after_tools_post_hook_gates_on_last_authored_lesson():
    assert nodes.route_after_tools_post_hook({"last_authored_lesson": {"tool": "draftAddLesson"}}, {}) == "critic_node"
    assert nodes.route_after_tools_post_hook({}, {}) == "chat_node"


# ---------------------------------------------------------------------------
# critic_node aggregates draft* tool names like their frontend counterparts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_critic_node_aggregates_draftAppendLessonContent():
    from agent import nodes as N
    state = {
        "last_authored_lesson": {
            "lesson_id": "les-1",
            "tool": "draftAppendLessonContent",
            "blocks": [{"type": "heading", "props": {"level": 2}, "content": [{"type": "text", "text": "Practice"}], "children": []}],
            "title": None,
        },
        "lesson_blocks_cache": {
            "les-1": [
                {"type": "heading", "props": {"level": 1}, "content": [{"type": "text", "text": "Title"}], "children": []},
            ],
        },
    }
    out = await N.critic_node(state, {})
    cache = out["lesson_blocks_cache"]["les-1"]
    assert len(cache) == 2  # appended, not replaced
    assert out["last_authored_lesson"] is None


@pytest.mark.asyncio
async def test_critic_node_defers_on_draftPatchLessonBlocks():
    from agent import nodes as N
    state = {"last_authored_lesson": {"tool": "draftPatchLessonBlocks", "lesson_id": "les-1"}}
    out = await N.critic_node(state, {})
    assert out == {"last_authored_lesson": None}


# ---------------------------------------------------------------------------
# Frontend-tool shadow filter
# ---------------------------------------------------------------------------

def test_frontend_tool_filter_drops_persistent_lesson_mutations(monkeypatch):
    monkeypatch.delenv("AGENT_FILTER_PERSISTENT_FRONTEND_MUTATIONS", raising=False)
    cfg = {
        "configurable": {
            "frontend_tools": [
                {"name": "addLesson", "description": "shadowed"},
                {"name": "askUser", "description": "ok"},
                {"name": "patchLessonBlocks", "description": "shadowed"},
            ]
        }
    }
    defs = nodes._frontend_tool_defs(cfg)
    names = {d["function"]["name"] for d in defs}
    assert "addLesson" not in names
    assert "patchLessonBlocks" not in names
    assert "askUser" in names


def test_frontend_tool_filter_can_be_disabled_via_env(monkeypatch):
    monkeypatch.setenv("AGENT_FILTER_PERSISTENT_FRONTEND_MUTATIONS", "0")
    cfg = {
        "configurable": {
            "frontend_tools": [
                {"name": "addLesson", "description": "legacy"},
                {"name": "askUser", "description": "ok"},
            ]
        }
    }
    names = {d["function"]["name"] for d in nodes._frontend_tool_defs(cfg)}
    assert names == {"addLesson", "askUser"}


# ---------------------------------------------------------------------------
# State-conditional prompt trim
# ---------------------------------------------------------------------------

def test_prompt_trimmed_on_greeting_turn():
    state = {"messages": [HumanMessage(content="hi!")]}
    prompt = build_system_prompt(state, [])
    assert "CONVERSATIONAL OPENING" in prompt  # ROLE kept
    assert "WORKING LOOP" not in prompt  # LOOP skipped
    assert "VERIFY BEFORE ACT" not in prompt
    assert "BATCHED LESSON AUTHORING" not in prompt
    assert "QUALITY GATE" not in prompt


def test_prompt_includes_working_loop_on_authoring_intent():
    state = {"messages": [HumanMessage(content="Please create a syllabus for grade 3 math")]}
    prompt = build_system_prompt(state, [])
    assert "WORKING LOOP" in prompt
    assert "BATCHED LESSON AUTHORING" in prompt


def test_prompt_includes_working_loop_when_editor_context_present():
    state = {"messages": [HumanMessage(content="thanks!")]}
    prompt = build_system_prompt(state, [], editor_context_override={"syllabus": {"id": "s1"}})
    assert "WORKING LOOP" in prompt


def test_prompt_includes_working_loop_when_critic_feedback_pending():
    state = {"messages": [HumanMessage(content="ok")]}
    prompt = build_system_prompt(state, [], critic_feedback="Fix missing Sources section.")
    assert "REVISION REQUIRED" in prompt
    assert "WORKING LOOP" in prompt
