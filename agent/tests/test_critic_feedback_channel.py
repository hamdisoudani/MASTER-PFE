"""Lifecycle test for the `critic_feedback` state channel.

Ensures the critic node no longer pollutes `messages` with SystemMessage
instances, and that chat_node consumes + clears the feedback on the next
turn so the UI never sees it.
"""
from __future__ import annotations

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


def test_critic_writes_to_channel_not_messages(monkeypatch):
    bad_blocks = [{"type": "heading", "text": "x"}]
    monkeypatch.setattr(
        critic_mod,
        "evaluate_lesson",
        lambda blocks: {"pass": False, "issues": ["too short"], "stats": {"blocks": 1}},
    )

    ai = AIMessage(
        content="",
        tool_calls=[{"id": "c1", "name": "addLesson",
                     "args": {"chapter_id": "ch1", "title": "Intro", "blocks": bad_blocks}}],
    )
    state = _fake_state([HumanMessage(content="write lesson"), ai])
    out = critic_mod.critic_node(state)

    assert "critic_feedback" in out, "critic must write to the dedicated channel"
    assert isinstance(out["critic_feedback"], str)
    assert "too short" in out["critic_feedback"]
    for m in out.get("messages", []):
        assert not isinstance(m, SystemMessage), "critic must not append SystemMessage to messages"


def test_chat_node_consumes_and_clears_feedback(monkeypatch):
    seen = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        return "SYSTEM PROMPT WITH FEEDBACK"

    monkeypatch.setattr(nodes_mod, "build_system_prompt", fake_build)
    monkeypatch.setattr(nodes_mod, "_invoke_model",
                        lambda sys, msgs, **kw: AIMessage(content="ok"))

    state = _fake_state([HumanMessage(content="retry")], feedback="FIX: add 3 blocks")
    out = nodes_mod.chat_node(state)

    assert seen.get("critic_feedback") == "FIX: add 3 blocks"
    assert out.get("critic_feedback") is None, "chat_node must clear the channel after use"
