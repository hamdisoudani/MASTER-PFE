"""Pure-LangGraph ReAct nodes with a deterministic critic gate.

Architecture (see state.py for channel docs):

    chat_node ──tools?──▶ ToolNode ─────────────────────────┐
        │                                                    │
        └──frontend?──▶ frontend_tool_node ──mutation?──▶ critic_node
                                    │                         │
                                    └─── else ────────────────┤
                                                              ▼
                                                          chat_node | END

Cleanliness invariants (enforced here):

1. ``messages`` is the UI channel. Only three producers append to it:
   - the LLM in ``chat_node`` (assistant replies + tool_call shells)
   - ``ToolNode`` / ``frontend_tool_node`` (ToolMessages the UI renders)
   - the ``publish()`` helper for user-facing status lines
2. Every other internal signal (critic feedback, user-rejection guidance,
   compact-history summaries) flows through typed state channels:
   ``critic_feedback`` (str), ``critique`` (dict), ``stop_reason``.
3. Residual internal items that *must* ride ``messages`` (edge cases) are
   tagged with ``additional_kwargs={"internal": True}`` and hidden by the
   ChatPane ``hiddenMessageIds`` filter.
4. GC (``agent.gc.gc_state``) runs at the top of every chat turn so the
   checkpointer stores a lean delta.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt

from agent.critic import (
    MAX_REVISIONS,
    evaluate_lesson,
    format_exhausted,
    format_feedback,
    structured_critique,
)
from agent.gc import gc_state
from agent.llm import get_llm, get_model_family
from agent.middleware import (
    compact_history,
    ensure_no_empty_ai,
    estimate_context_usage,
    gc_persistent_messages,
    normalize_system_messages,
)
from agent.prompts import build_system_prompt
from agent.state import AgentState
from agent.tools import PYTHON_TOOLS, PYTHON_TOOL_NAMES

logger = logging.getLogger(__name__)

CONTEXT_TOKEN_BUDGET = int(os.getenv("AGENT_CONTEXT_TOKEN_BUDGET", "128000"))

LESSON_MUTATION_TOOLS = {
    "addLesson",
    "updateLessonContent",
    "appendLessonContent",
    "patchLessonBlocks",
}


# ---------------------------------------------------------------------------
# publish() — the ONLY sanctioned way to append a user-visible message.
# ---------------------------------------------------------------------------

def publish(text: str, *, kind: str = "assistant") -> AIMessage:
    """Build a UI-visible assistant message. Grep for ``publish(`` to audit
    every surface the user sees from internal nodes."""
    return AIMessage(content=text, additional_kwargs={"ui": True, "kind": kind})


def _internal_note(text: str, *, kind: str = "system-note") -> SystemMessage:
    """Tag a SystemMessage as internal so ChatPane's ``hiddenMessageIds``
    filter drops it. Prefer typed state channels; use this only as a
    last-resort when a node must ride ``messages`` for wiring reasons."""
    return SystemMessage(content=text, additional_kwargs={"internal": True, "kind": kind})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frontend_tool_defs(config: RunnableConfig) -> list[dict[str, Any]]:
    cfg = (config or {}).get("configurable", {}) or {}
    schemas = cfg.get("frontend_tools") or []
    out: list[dict[str, Any]] = []
    for item in schemas:
        name = item.get("name")
        if not name:
            continue
        params = item.get("parameters") or {"type": "object", "properties": {}}
        fn: dict[str, Any] = {
            "name": name,
            "description": item.get("description", ""),
            "parameters": params,
        }
        if item.get("strict") is True:
            fn["strict"] = True
        out.append({"type": "function", "function": fn})
    return out


def _frontend_tool_names(config: RunnableConfig) -> set[str]:
    return {
        d["function"]["name"]
        for d in _frontend_tool_defs(config)
        if d.get("function", {}).get("name")
    }


def _was_user_rejected(resume_value: Any) -> bool:
    if isinstance(resume_value, dict):
        if resume_value.get("rejected") is True:
            return True
        status = resume_value.get("status")
        if isinstance(status, str) and status.lower() in {"rejected", "cancelled", "canceled"}:
            return True
    return False


# ---------------------------------------------------------------------------
# chat_node
# ---------------------------------------------------------------------------

async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    llm = get_llm()
    frontend_defs = _frontend_tool_defs(config)
    all_tools: list[Any] = list(PYTHON_TOOLS) + list(frontend_defs)

    parallel_env = os.getenv("LLM_PARALLEL_TOOLS")
    if parallel_env is not None:
        parallel = parallel_env == "1"
    else:
        parallel = get_model_family() != "mistral"
    bound = llm.bind_tools(all_tools, parallel_tool_calls=parallel)

    # 1) Compact + normalize the persisted thread.
    raw = list(state.get("messages", []))
    compacted = compact_history(raw, token_budget=CONTEXT_TOKEN_BUDGET)
    compacted = ensure_no_empty_ai(compacted)
    messages = normalize_system_messages(compacted)
    context_usage = estimate_context_usage(messages, CONTEXT_TOKEN_BUDGET)

    cfg = (config or {}).get("configurable", {}) or {}
    editor_ctx = cfg.get("editor_context")
    if editor_ctx is None:
        editor_ctx = state.get("editor_context")
    thread_id = cfg.get("thread_id")

    # 2) Build a fresh, authoritative system prompt every turn. Includes the
    #    pending critic feedback (if any) so the LLM actually sees it —
    #    unlike the old path where SystemMessage-in-messages was stripped
    #    by normalize_system_messages before the LLM was called.
    critic_feedback = state.get("critic_feedback")
    system_prompt = build_system_prompt(
        state,
        _frontend_tool_defs(config),
        editor_ctx,
        thread_id=thread_id,
        critic_feedback=critic_feedback,
    )
    full_messages: list[BaseMessage] = [SystemMessage(content=system_prompt)] + messages

    # 3) Call the model.
    try:
        response: AIMessage = await bound.ainvoke(full_messages, config)
    except Exception as e:  # noqa: BLE001
        logger.exception("chat_node LLM call failed")
        err_payload = {"message": str(e) or repr(e), "type": type(e).__name__}
        err_msg = AIMessage(
            content=("⚠️ The run failed: " + (err_payload["message"][:500] or err_payload["type"])),
            additional_kwargs={"error": err_payload, "ui": True, "kind": "error"},
        )
        return {"messages": [err_msg], "stop_reason": "error"}

    has_tool_calls = bool(getattr(response, "tool_calls", None))

    # 4) GC — both the persistent message log AND the heavy state channels.
    gc_msg_updates = gc_persistent_messages(raw)
    gc_state_update = gc_state(state)

    out: dict[str, Any] = {
        "messages": [*gc_msg_updates, response],
        "context_usage": context_usage,
        **gc_state_update,
    }
    # Clear the critic_feedback we just consumed so it does not re-fire.
    if critic_feedback is not None:
        out["critic_feedback"] = None
    if not has_tool_calls:
        out["stop_reason"] = "completed"
    return out


# ---------------------------------------------------------------------------
# frontend_tool_node
# ---------------------------------------------------------------------------

async def frontend_tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Emit a LangGraph ``interrupt`` for every frontend tool call so the
    browser can execute the mutation locally. Capture the latest lesson
    mutation for the critic. Do NOT append any SystemMessage prose to
    ``messages`` — rejection guidance flows via ``critic_feedback``."""
    messages = state.get("messages", [])
    if not messages:
        return {}
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return {}
    tool_calls = list(getattr(last, "tool_calls", None) or [])
    if not tool_calls:
        return {}

    frontend_names = _frontend_tool_names(config)
    fe_calls = [tc for tc in tool_calls if tc.get("name") in frontend_names]
    if not fe_calls:
        return {}

    tool_messages: list[BaseMessage] = []
    last_lesson: dict[str, Any] | None = None
    any_rejected = False

    for tc in fe_calls:
        try:
            resume_value = interrupt(
                {
                    "type": "frontend_tool_call",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "args": tc.get("args") or {},
                }
            )
        except GraphInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("frontend tool interrupt failed")
            tool_messages.append(
                ToolMessage(
                    content=json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
                    tool_call_id=tc["id"],
                    status="error",
                )
            )
            continue

        if _was_user_rejected(resume_value):
            any_rejected = True

        if tc["name"] in LESSON_MUTATION_TOOLS and not _was_user_rejected(resume_value):
            args = tc.get("args") or {}
            lesson_id = args.get("lessonId") or args.get("chapterId") or "unknown"
            if tc["name"] == "patchLessonBlocks":
                blocks = args.get("blocks")
            elif tc["name"] == "appendLessonContent":
                blocks = args.get("blocks")
            else:
                blocks = args.get("content")
            blocks_list = blocks if isinstance(blocks, list) else []
            last_lesson = {
                "lesson_id": lesson_id,
                "tool": tc["name"],
                "blocks": blocks_list,
                "title": args.get("title"),
            }

        if isinstance(resume_value, (dict, list)):
            content = json.dumps(resume_value)
        elif resume_value is None:
            content = "ok"
        else:
            content = str(resume_value)
        tool_messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))

    out: dict[str, Any] = {"messages": list(tool_messages)}
    if any_rejected:
        # Route guidance through the internal channel, not messages.
        out["critic_feedback"] = (
            "The user rejected your last tool call. Do NOT retry the same mutation. "
            "Ask the user briefly what they want changed, or propose an alternative."
        )
        out["stop_reason"] = "interrupted_by_user"
    if last_lesson is not None:
        out["last_authored_lesson"] = last_lesson
    return out


# ---------------------------------------------------------------------------
# critic_node — deterministic gate. No LLM. No UI pollution.
# ---------------------------------------------------------------------------

async def critic_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    lesson = state.get("last_authored_lesson") or None
    if not lesson:
        return {}

    # patchLessonBlocks only carries a partial patch — defer rubric until
    # the agent re-reads the full lesson.
    if lesson.get("tool") == "patchLessonBlocks":
        return {"last_authored_lesson": None}

    lesson_id = str(lesson.get("lesson_id") or "unknown")
    tool_name = lesson.get("tool")
    title = lesson.get("title")
    batch_blocks = lesson.get("blocks") or []

    # Aggregate batched authoring (addLesson + appendLessonContent).
    cache = dict(state.get("lesson_blocks_cache") or {})
    if tool_name == "addLesson":
        cache[lesson_id] = list(batch_blocks)
        aggregated = cache[lesson_id]
    elif tool_name == "appendLessonContent":
        aggregated = list(cache.get(lesson_id) or []) + list(batch_blocks)
        cache[lesson_id] = aggregated
    else:  # updateLessonContent — full overwrite
        cache[lesson_id] = list(batch_blocks)
        aggregated = cache[lesson_id]

    report = evaluate_lesson(aggregated)
    critique = structured_critique(lesson_id, report, tool=tool_name, title=title)

    attempts = dict(state.get("revision_attempts") or {})
    reports = dict(state.get("critic_reports") or {})
    reports[lesson_id] = {
        **report,
        "tool": tool_name,
        "title": title,
        "block_count": len(aggregated),
    }

    out: dict[str, Any] = {
        "critic_reports": reports,
        "critique": critique,
        "last_authored_lesson": None,
        "lesson_blocks_cache": cache,
    }

    if report.get("pass"):
        attempts.pop(lesson_id, None)
        out["revision_attempts"] = attempts
        out["critic_feedback"] = None
        return out

    current = attempts.get(lesson_id, 0) + 1
    attempts[lesson_id] = current
    out["revision_attempts"] = attempts

    if current > MAX_REVISIONS:
        # Tell the user ONCE, via the UI-visible publish channel.
        out["messages"] = [publish(format_exhausted(lesson_id, report), kind="quality-exhausted")]
        out["critic_feedback"] = None
        out["stop_reason"] = "quality_gate_exhausted"
        return out

    # Internal fix instructions — consumed by chat_node, never rendered.
    out["critic_feedback"] = format_feedback(lesson_id, report)
    return out


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

def route_after_chat(state: AgentState, config: RunnableConfig) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return "end"
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return "end"

    frontend_names = _frontend_tool_names(config)
    has_frontend = any(tc["name"] in frontend_names for tc in tool_calls)
    has_python = any(tc["name"] in PYTHON_TOOL_NAMES for tc in tool_calls)

    if has_frontend:
        return "frontend_tools"
    if has_python:
        return "tools"
    return "end"


def route_after_frontend_tools(state: AgentState, config: RunnableConfig) -> str:
    if state.get("stop_reason") == "interrupted_by_user":
        return "chat_node"
    if state.get("last_authored_lesson"):
        return "critic_node"
    return "chat_node"


def route_after_tools_python(state: AgentState, config: RunnableConfig) -> str:
    return "chat_node"


def route_after_critic(state: AgentState, config: RunnableConfig) -> str:
    if state.get("stop_reason") == "quality_gate_exhausted":
        return "end"
    return "chat_node"
