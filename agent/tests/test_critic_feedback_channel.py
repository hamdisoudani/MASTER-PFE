"""Lifecycle test for the `critic_feedback` state channel.

Ensures the critic node no longer pollutes `messages` with SystemMessage
instances, and that chat_node consumes + clears the feedback on the next
turn so the UI never sees it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent import critic as critic_mod
from agent import nodes as nodes_mod


def _fake_state(messages, feedback=None):
    return {
        "messages": list(messages),
        "critic_feedback": feedback,
        "thread_id": "t-test",
    }


@pytest.mark.asyncio
async def test_critic_writes_to_channel_not_messages(monkeypatch):
    bad_blocks = [{"type": "heading", "text": "x"}]
    monkeypatch.setattr(
        critic_mod,
        "evaluate_lesson",
        lambda blocks: {"pass": False, "issues": ["too short"], "stats": {"blocks": 1}},
    )

    tool_msg = SimpleNamespace(
        type="tool",
        name="addLesson",
        tool_call_id="c1",
        content="{}",
        artifact=None,
    )
    ai = AIMessage(
        content="",
        tool_calls=[{"id": "c1", "name": "addLesson",
                     "args": {"chapter_id": "ch1", "lesson_id": "L1",
                              "title": "Intro", "blocks": bad_blocks}}],
    )
    state = _fake_state([HumanMessage(content="write lesson"), ai, tool_msg])
    state["last_authored_lesson"] = {
        "lesson_id": "L1",
        "chapter_id": "ch1",
        "title": "Intro",
        "blocks": bad_blocks,
        "tool": "addLesson",
    }

    out = await nodes_mod.critic_node(state, {})

    assert isinstance(out.get("critic_feedback"), str)
    assert out["critic_feedback"], "critic must produce a non-empty feedback message"
    assert "lesson" in out["critic_feedback"].lower() or "quality" in out["critic_feedback"].lower()
    for m in out.get("messages", []) or []:
        assert not isinstance(m, SystemMessage), (
            "critic must not append SystemMessage to messages"
        )


@pytest.mark.asyncio
async def test_chat_node_consumes_and_clears_feedback(monkeypatch):
    seen = {}

    def fake_build(state, frontend_defs, editor_ctx, *, thread_id=None,
                   critic_feedback=None, **kw):
        seen["critic_feedback"] = critic_feedback
        return "SYSTEM PROMPT WITH FEEDBACK"

    class FakeBound:
        async def ainvoke(self, msgs, config=None):
            return AIMessage(content="ok")

    class FakeLLM:
        def bind_tools(self, tools, **kw):
            return FakeBound()

    monkeypatch.setattr(nodes_mod, "build_system_prompt", fake_build)
    monkeypatch.setattr(nodes_mod, "get_llm", lambda: FakeLLM())

    state = _fake_state([HumanMessage(content="retry")], feedback="FIX: add 3 blocks")
    out = await nodes_mod.chat_node(state, {})

    assert seen.get("critic_feedback") == "FIX: add 3 blocks"
    assert out.get("critic_feedback") is None, (
        "chat_node must clear the channel after use"
    )
