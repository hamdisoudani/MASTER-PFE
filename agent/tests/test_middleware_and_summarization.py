"""Unit tests for middleware + deep_graph summarization safety.

Goal: guarantee the bug "System message must be at the beginning" cannot
recur, regardless of whether the summarizer comes from our classic
``compact_history`` path or from langchain's ``SummarizationMiddleware``
used by the deep graph.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.middleware import (
    compact_history,
    estimate_context_usage,
    ensure_no_empty_ai,
    normalize_system_messages,
)


def test_normalize_strips_all_system_messages():
    msgs = [
        SystemMessage(content="old supervisor prompt"),
        HumanMessage(content="hi"),
        AIMessage(content="ok"),
        SystemMessage(content="critic feedback: fix X"),
        HumanMessage(content="please retry"),
    ]
    out = normalize_system_messages(msgs)
    assert all(not isinstance(m, SystemMessage) for m in out), "no SystemMessage should remain"
    assert out[0].content.startswith("[system-note]")
    assert out[3].content.startswith("[system-note] critic feedback")


def test_compact_history_emits_no_system_message():
    big = "x" * 100000
    msgs = []
    for i in range(40):
        msgs.append(HumanMessage(content=f"q{i} {big}"))
        msgs.append(AIMessage(content=f"a{i} {big}"))
    out = compact_history(msgs, token_budget=2000)
    assert out, "compact_history must return messages"
    assert not any(isinstance(m, SystemMessage) for m in out), (
        "compact_history must not inject a mid-thread SystemMessage"
    )
    assert "[compact-summary]" in (out[0].content if isinstance(out[0].content, str) else ""), (
        "first compacted message should carry the summary tag"
    )


def test_full_pipeline_has_zero_system_messages_in_thread():
    msgs = [
        SystemMessage(content="stale system"),
        HumanMessage(content="write lesson 1"),
        AIMessage(content="starting"),
        SystemMessage(content="QUALITY REVIEW FAILED..."),
        HumanMessage(content="go"),
    ]
    compacted = compact_history(msgs, token_budget=999999)
    compacted = ensure_no_empty_ai(compacted)
    cleaned = normalize_system_messages(compacted)
    assert all(not isinstance(m, SystemMessage) for m in cleaned)


def test_estimate_context_usage_shape():
    msgs = [HumanMessage(content="a" * 4000)]
    u = estimate_context_usage(msgs, budget=10000)
    assert set(u.keys()) == {"tokens", "budget", "fraction"}
    assert u["budget"] == 10000
    assert 0.0 <= u["fraction"] <= 1.0
    assert u["tokens"] > 0


def test_tool_bond_preserved_through_compaction():
    msgs = [HumanMessage(content="hi")]
    big = "y" * 80000
    for i in range(20):
        ai = AIMessage(
            content="",
            tool_calls=[{"id": f"t{i}", "name": "web_search", "args": {"q": big}}],
        )
        tm = ToolMessage(content=f"res{i}", tool_call_id=f"t{i}")
        msgs.extend([HumanMessage(content=f"turn{i}"), ai, tm])
    out = compact_history(msgs, token_budget=5000)
    open_calls = set()
    for m in out:
        if isinstance(m, AIMessage):
            for tc in (m.tool_calls or []):
                open_calls.add(tc["id"])
        elif isinstance(m, ToolMessage):
            open_calls.discard(m.tool_call_id)
    assert not open_calls, f"orphan tool_calls after compaction: {open_calls}"


def test_deep_graph_builds_without_backend_module():
    """Regression: deep_graph.py must not import deepagents.backends.

    Also verifies SummarizationMiddleware is wired into both supervisor
    and subagent middleware stacks so long runs compact safely.
    """
    import os
    os.environ.setdefault("LLM_API_KEY", "test")
    os.environ.setdefault("LLM_MODEL", "mistralai/mistral-small-4-119b-2603")
    import importlib, agent.deep_graph as dg
    importlib.reload(dg)
    assert hasattr(dg, "graph")
    assert hasattr(dg, "_make_summarizer")
    mw = dg._make_summarizer()
    from langchain.agents.middleware import SummarizationMiddleware
    assert isinstance(mw, SummarizationMiddleware)
