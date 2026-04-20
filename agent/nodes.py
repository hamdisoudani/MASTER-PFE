"""Pure-LangGraph ReAct nodes with a deterministic critic gate.

- `chat_node` calls the LLM with Python tools + frontend tool schemas.
- When the LLM calls a Python tool, we route to the built-in `ToolNode`.
- When the LLM calls a *frontend* tool, we route to `frontend_tool_node`
  which calls `langgraph.types.interrupt(...)` so the browser can execute
  the mutation locally.
- After every `frontend_tools` return, `critic_node` inspects whether a
  lesson-mutating tool ran and applies a deterministic rubric to the
  block array the agent sent. On failure we inject a SystemMessage with
  concrete fix instructions and loop back to chat_node; on pass we
  continue normally.
- Scraped sources from `scrape_page` are mirrored into `research_cache`
  so the writer can rely on them even after `compact_history` elides
  the raw tool output from the chat thread.

Context/robustness middleware (see agent/middleware.py) is applied inside
`chat_node` before every model call, ported from langchain-ai/open-swe.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt

from agent.critic import MAX_REVISIONS, evaluate_lesson, format_feedback
from agent.llm import get_llm, get_model_family
from agent.middleware import compact_history, ensure_no_empty_ai, estimate_context_usage, gc_persistent_messages, normalize_system_messages
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

    raw = list(state.get("messages", []))
    compacted = compact_history(raw, token_budget=CONTEXT_TOKEN_BUDGET)
    compacted = ensure_no_empty_ai(compacted)
    messages = normalize_system_messages(compacted)
    context_usage = estimate_context_usage(messages, CONTEXT_TOKEN_BUDGET)

    cfg = (config or {}).get("configurable", {}) or {}
    editor_ctx = cfg.get("editor_context")
    if editor_ctx is None:
        editor_ctx = state.get("editor_context")

    full_messages = [
        SystemMessage(content=build_system_prompt(state, _frontend_tool_defs(config), editor_ctx))
    ] + messages

    try:
        response: AIMessage = await bound.ainvoke(full_messages, config)
    except Exception as e:  # noqa: BLE001
        logger.exception("chat_node LLM call failed")
        err_payload = {"message": str(e) or repr(e), "type": type(e).__name__}
        err_msg = AIMessage(
            content=("⚠️ The run failed: " + (err_payload["message"][:500] or err_payload["type"])),
            additional_kwargs={"error": err_payload},
        )
        return {"messages": [err_msg], "stop_reason": "error"}

    has_tool_calls = bool(getattr(response, "tool_calls", None))
    gc_updates = gc_persistent_messages(raw)
    out: dict[str, Any] = {
        "messages": [*gc_updates, response],
        "context_usage": context_usage,
    }
    if not has_tool_calls:
        out["stop_reason"] = "completed"
    return out


def _was_user_rejected(resume_value: Any) -> bool:
    return isinstance(resume_value, dict) and resume_value.get("error") == "user_rejected"


def _cache_scrape_result(state: AgentState, tool_name: str, args: dict[str, Any], result_text: str) -> dict[str, Any]:
    """Mirror scrape_page outputs into research_cache keyed by the URL.

    We store a trimmed markdown so the writer can grep/cite without
    re-scraping and without keeping the full payload in message history.
    """
    if tool_name != "scrape_page":
        return {}
    url = (args or {}).get("url") or "unknown"
    cache = dict(state.get("research_cache") or {})
    bucket_key = args.get("lesson_id") or args.get("topic") or "_global"
    bucket = list(cache.get(bucket_key) or [])
    if any(entry.get("url") == url for entry in bucket):
        return {}
    bucket.append({
        "url": url,
        "title": (result_text.splitlines()[0][:200] if result_text else url),
        "markdown": (result_text or "")[:4000],
    })
    cache[bucket_key] = bucket
    return {"research_cache": cache}


async def frontend_tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    messages = list(state.get("messages", []))
    if not messages or not isinstance(messages[-1], AIMessage):
        return {}
    last: AIMessage = messages[-1]
    frontend_names = _frontend_tool_names(config)

    tool_messages: list[ToolMessage] = []
    any_rejected = False
    last_lesson: dict[str, Any] | None = None

    for tc in last.tool_calls or []:
        if tc["name"] not in frontend_names:
            continue
        try:
            resume_value: Any = interrupt(
                {
                    "type": "frontend_tool_call",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "args": tc.get("args") or {},
                }
            )
        except GraphInterrupt:
            # `interrupt()` raises GraphInterrupt to pause the graph so the
            # browser can execute the tool and resume with a value. This is
            # NOT an error path — re-raise so LangGraph can surface the
            # interrupt to the SDK / useStream consumer.
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
        out["messages"].append(SystemMessage(
            content=(
                "The user rejected your last tool call. Do NOT retry the same mutation. "
                "Ask the user briefly what they want changed, or propose an alternative."
            )
        ))
        out["stop_reason"] = "interrupted_by_user"
    if last_lesson is not None:
        out["last_authored_lesson"] = last_lesson
    return out


async def critic_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Deterministic quality gate.

    Runs after frontend_tool_node when a lesson mutation just happened.
    For `patchLessonBlocks` we only have the patch (not the full lesson)
    so we skip strict rubric and rely on the critic to re-engage once
    the agent re-reads the lesson — we still log the intent.
    """
    lesson = state.get("last_authored_lesson") or None
    if not lesson:
        return {}

    if lesson.get("tool") == "patchLessonBlocks":
        return {"last_authored_lesson": None}

    lesson_id = str(lesson.get("lesson_id") or "unknown")
    tool_name = lesson.get("tool")
    batch_blocks = lesson.get("blocks") or []

    # Aggregate blocks across addLesson + appendLessonContent batches. The
    # supervisor/writer authors lessons in 2-3 batches per the BATCH_WRITING
    # policy, so we only evaluate the full lesson on the latest append for
    # a given lessonId — earlier batches cache their blocks and skip.
    cache = dict(state.get("lesson_blocks_cache") or {})
    if tool_name == "addLesson":
        cache[lesson_id] = list(batch_blocks)
        aggregated = cache[lesson_id]
    elif tool_name == "appendLessonContent":
        aggregated = list(cache.get(lesson_id) or []) + list(batch_blocks)
        cache[lesson_id] = aggregated
    else:  # updateLessonContent is a full overwrite
        cache[lesson_id] = list(batch_blocks)
        aggregated = cache[lesson_id]

    report = evaluate_lesson(aggregated)

    attempts = dict(state.get("revision_attempts") or {})
    reports = dict(state.get("critic_reports") or {})
    reports[lesson_id] = {**report, "tool": tool_name, "title": lesson.get("title"),
                          "block_count": len(aggregated)}

    out: dict[str, Any] = {
        "critic_reports": reports,
        "last_authored_lesson": None,
        "lesson_blocks_cache": cache,
    }

    if report.get("pass"):
        attempts.pop(lesson_id, None)
        out["revision_attempts"] = attempts
        return out

    current = attempts.get(lesson_id, 0) + 1
    attempts[lesson_id] = current
    out["revision_attempts"] = attempts

    if current > MAX_REVISIONS:
        out["messages"] = [SystemMessage(
            content=(
                f"Quality rubric still failing for lesson {lesson_id} after "
                f"{MAX_REVISIONS} revisions. Stop revising — briefly summarise the "
                "remaining gaps to the user and ask for guidance."
            )
        )]
        out["stop_reason"] = "quality_gate_exhausted"
        return out

    out["messages"] = [SystemMessage(content=format_feedback(lesson_id, report))]
    return out


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
    """If a lesson mutation happened, run the critic; otherwise resume chat."""
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
