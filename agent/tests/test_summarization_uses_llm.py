"""Both summarization paths must actually call the LLM.

- Classic graph: ``agent.middleware.compact_history`` -> ``_summarize_slice``
  must invoke ``agent.llm.get_llm()``'s returned chat model.
- Deep graph: ``langchain.agents.middleware.SummarizationMiddleware`` must
  hold a reference to our LLM via the ``model`` field.

We patch ``get_llm`` with a fake chat model that records invocations so the
test stays hermetic (no network, no key).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import agent.middleware as mw


class _RecorderLLM(FakeListChatModel):
    """Deterministic LLM that records .invoke() calls."""
    calls: list[list[Any]] = []

    def invoke(self, input, config=None, **kwargs):  # type: ignore[override]
        _RecorderLLM.calls.append(list(input) if isinstance(input, list) else [input])
        return super().invoke(input, config=config, **kwargs)


def _build_overflow_history(n_turns: int = 18) -> list:
    big = "Z" * 8000
    msgs: list = []
    for i in range(n_turns):
        msgs.append(HumanMessage(content=f"turn {i}: please research topic {i} — {big}"))
        msgs.append(AIMessage(
            content="",
            tool_calls=[{"id": f"t{i}", "name": "web_search", "args": {"q": f"q{i}"}}],
        ))
        msgs.append(ToolMessage(content=f"result {i} " + big, tool_call_id=f"t{i}"))
        msgs.append(AIMessage(content=f"assistant note {i}"))
    return msgs


def test_classic_compact_history_actually_calls_llm(monkeypatch):
    _RecorderLLM.calls = []
    fake = _RecorderLLM(responses=[
        "### User intent\nBuild a lesson series.\n"
        "### Lessons & artifacts produced so far\nlesson-2-1 drafted.\n"
        "### Tools used and key results\nweb_search x many\n"
        "### Open issues / pending todos\n- finish lesson-2-2\n"
        "### Decisions & constraints to preserve\nMistral provider."
    ])
    monkeypatch.setattr("agent.llm.get_llm", lambda: fake, raising=True)

    msgs = _build_overflow_history(20)
    out = mw.compact_history(msgs, token_budget=2000)

    assert _RecorderLLM.calls, "compact_history did not invoke the LLM"
    rendered = _RecorderLLM.calls[-1]
    assert any("### User intent" in getattr(m, "content", "") for m in rendered if hasattr(m, "content")), \
        "SUMMARY_PROMPT (with '### User intent' section) must be passed to the LLM"
    assert any("turn " in getattr(m, "content", "") for m in rendered if hasattr(m, "content")), \
        "transcript of the older window must be passed to the LLM"

    first = out[0]
    assert isinstance(first, HumanMessage)
    content = first.content
    assert content.startswith("[compact-summary]"), "summary must be tagged, not raw SystemMessage"
    assert "LLM-generated" in content, "classic path must emit the LLM-generated summary"
    assert "### User intent" in content


def test_classic_falls_back_to_deterministic_when_llm_errors(monkeypatch):
    class _Boom:
        def invoke(self, *a, **k):
            raise RuntimeError("simulated 401 from provider")
    monkeypatch.setattr("agent.llm.get_llm", lambda: _Boom(), raising=True)
    msgs = _build_overflow_history(20)
    out = mw.compact_history(msgs, token_budget=2000)
    first = out[0]
    assert isinstance(first, HumanMessage)
    assert "deterministic fallback" in first.content


def test_deep_graph_summarizer_holds_real_llm(monkeypatch):
    import os
    os.environ.setdefault("LLM_API_KEY", "test")
    os.environ.setdefault("LLM_MODEL", "mistralai/mistral-small-4-119b-2603")

    import importlib, agent.deep_graph as dg
    importlib.reload(dg)

    from langchain.agents.middleware import SummarizationMiddleware
    mw_instance = dg._make_summarizer()
    assert isinstance(mw_instance, SummarizationMiddleware)
    assert getattr(mw_instance, "model", None) is not None, "SummarizationMiddleware has no bound model"
    assert hasattr(mw_instance.model, "invoke"), "bound model must be an invokable chat model"



def test_compacted_summary_is_tagged_internal_for_ui(monkeypatch):
    """The summary HumanMessage must carry additional_kwargs.internal=True so
    the frontend can filter it out (otherwise it renders as a user bubble).
    """
    _RecorderLLM.calls = []
    fake = _RecorderLLM(responses=["### User intent\nx\n### Lessons & artifacts produced so far\ny\n### Tools used and key results\nz\n### Open issues / pending todos\nq\n### Decisions & constraints to preserve\nr"])
    monkeypatch.setattr("agent.llm.get_llm", lambda: fake, raising=True)
    msgs = _build_overflow_history(20)
    out = mw.compact_history(msgs, token_budget=2000)
    first = out[0]
    assert isinstance(first, HumanMessage)
    ak = getattr(first, "additional_kwargs", {}) or {}
    assert ak.get("internal") is True, "compact summary must be tagged internal"
    assert ak.get("kind") == "compact-summary"


def test_normalize_system_messages_tags_internal():
    from langchain_core.messages import SystemMessage
    msgs = [SystemMessage(content="QUALITY REVIEW FAILED: fix lesson-1"), HumanMessage(content="ok")]
    out = mw.normalize_system_messages(msgs)
    note = out[0]
    assert isinstance(note, HumanMessage)
    ak = getattr(note, "additional_kwargs", {}) or {}
    assert ak.get("internal") is True
    assert ak.get("kind") == "system-note"
