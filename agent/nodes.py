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

DRAFT_LESSON_MUTATION_TOOLS = {
    "draftAddLesson",
    "draftUpdateLessonContent",
    "draftAppendLessonContent",
    "draftPatchLessonBlocks",
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
        SystemMessage(content=build_system_prompt(state, _frontend_tool_defs(config), editor_ctx, thread_id=(cfg.get('thread_id') if isinstance(cfg, dict) else None)))
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
    real_thread_id = ""
    try:
        real_thread_id = str(cfg.get("thread_id") or "").strip()
    except Exception:
        real_thread_id = ""
    if has_tool_calls and real_thread_id:
        rewritten = False
        new_tool_calls = []
        for tc in (response.tool_calls or []):
            if tc.get("name") == "getOrCreateSyllabus":
                args = dict(tc.get("args") or {})
                if args.get("thread_id") != real_thread_id:
                    logger.info(
                        "overriding getOrCreateSyllabus thread_id: %r -> %r",
                        args.get("thread_id"), real_thread_id,
                    )
                    args["thread_id"] = real_thread_id
                    tc = {**tc, "args": args}
                    rewritten = True
            new_tool_calls.append(tc)
        if rewritten:
            try:
                response.tool_calls = new_tool_calls  # type: ignore[attr-defined]
            except Exception:
                pass
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

    if lesson.get("tool") in ("patchLessonBlocks", "draftPatchLessonBlocks"):
        return {"last_authored_lesson": None}

    lesson_id = str(lesson.get("lesson_id") or "unknown")
    tool_name = lesson.get("tool")
    batch_blocks = lesson.get("blocks") or []

    # Aggregate blocks across addLesson + appendLessonContent batches. The
    # supervisor/writer authors lessons in 2-3 batches per the BATCH_WRITING
    # policy, so we only evaluate the full lesson on the latest append for
    # a given lessonId — earlier batches cache their blocks and skip.
    cache = dict(state.get("lesson_blocks_cache") or {})
    if tool_name in ("addLesson", "draftAddLesson"):
        cache[lesson_id] = list(batch_blocks)
        aggregated = cache[lesson_id]
    elif tool_name in ("appendLessonContent", "draftAppendLessonContent"):
        aggregated = list(cache.get(lesson_id) or []) + list(batch_blocks)
        cache[lesson_id] = aggregated
    else:  # updateLessonContent / draftUpdateLessonContent are full overwrites
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


async def tools_post_hook(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Runs after the Python/MCP ToolNode.

    Two jobs:
      1. If the model just called ``submit_plan``, lift the plan from
         the tool_call args into agent state and flip phase to "writing".
      2. If the model just called any ``draft*`` lesson mutation, mirror
         its payload into ``last_authored_lesson`` so ``critic_node``
         can run the deterministic rubric — same signal the frontend
         mutation path already produces.
    """
    messages = list(state.get("messages", []))
    if not messages:
        return {}
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai is None:
        return {}

    tool_msgs = []
    for m in reversed(messages):
        if isinstance(m, ToolMessage):
            tool_msgs.append(m)
        elif isinstance(m, AIMessage):
            break
    tool_msgs.reverse()
    results_by_call_id = {tm.tool_call_id: tm for tm in tool_msgs}

    update: dict[str, Any] = {}

    for tc in (last_ai.tool_calls or []):
        if tc.get("name") != "submit_plan":
            continue
        args = tc.get("args") or {}
        steps = args.get("steps") or []
        normalized = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            normalized.append({
                "chapter_title": str(step.get("chapter_title") or "").strip(),
                "lesson_title": str(step.get("lesson_title") or "").strip(),
                "brief": str(step.get("brief") or "").strip(),
                "status": "pending",
                "attempts": 0,
                "draft_lesson_id": None,
            })
        if normalized:
            update["plan"] = normalized
            update["plan_cursor"] = 0
            update["phase"] = "writing"
            logger.info("submit_plan registered: %d steps", len(normalized))
        break

    last_draft_mutation: dict[str, Any] | None = None
    for tc in (last_ai.tool_calls or []):
        name = tc.get("name")
        if name not in DRAFT_LESSON_MUTATION_TOOLS:
            continue
        args = tc.get("args") or {}
        blocks = args.get("blocks") if name != "draftPatchLessonBlocks" else args.get("patches")
        blocks_list = blocks if isinstance(blocks, list) else []

        lesson_id = args.get("lesson_id") or args.get("lessonId")
        if not lesson_id and name == "draftAddLesson":
            tm = results_by_call_id.get(tc.get("id"))
            if tm is not None:
                try:
                    parsed = json.loads(tm.content) if isinstance(tm.content, str) else None
                    if isinstance(parsed, dict):
                        lesson_id = parsed.get("id") or parsed.get("lesson_id")
                except Exception:
                    lesson_id = None
        lesson_id = lesson_id or f"new:{(args.get('title') or '').strip() or 'unknown'}"

        last_draft_mutation = {
            "lesson_id": str(lesson_id),
            "tool": name,
            "blocks": blocks_list,
            "title": args.get("title"),
        }

    if last_draft_mutation is not None:
        update["last_authored_lesson"] = last_draft_mutation

    return update


def route_after_python_tools(state: AgentState, config: RunnableConfig) -> str:
    """After the python/MCP tools + post-hook: critic if a draft lesson
    mutation happened, otherwise resume chat_node."""
    if state.get("last_authored_lesson"):
        return "critic_node"
    return "chat_node"


def _plan_summary(plan: list[dict[str, Any]], cursor: int) -> str:
    if not plan:
        return ""
    lines = []
    for i, step in enumerate(plan):
        marker = "→" if i == cursor else " "
        status = step.get("status") or "pending"
        lines.append(f"  {marker} [{i+1}/{len(plan)}] ({status}) "
                     f"{step.get('chapter_title','?')} :: {step.get('lesson_title','?')}")
    return "\n".join(lines)


def plan_router(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Deterministic plan advancement after the critic.

    Runs only when the syllabus_agent is in the "writing" phase and has
    a registered plan. Marks the current step's status based on the
    latest critic report, advances the cursor, and injects a concise
    SystemMessage telling the writer which lesson to author next — or
    flipping to the "promoting" phase once every step has passed.
    """
    phase = state.get("phase") or "planning"
    plan = state.get("plan") or []
    if phase != "writing" or not plan:
        return {}

    cursor = int(state.get("plan_cursor") or 0)
    cursor = max(0, min(cursor, len(plan) - 1))
    plan = [dict(s) for s in plan]
    current = plan[cursor]

    reports = state.get("critic_reports") or {}
    last = state.get("last_authored_lesson")
    lesson_id = (last or {}).get("lesson_id")
    report = reports.get(lesson_id) if lesson_id else None

    attempts = int(state.get("revision_attempts", {}).get(lesson_id, 0) if lesson_id else 0)
    current["attempts"] = attempts
    if lesson_id and not str(lesson_id).startswith("new:"):
        current["draft_lesson_id"] = lesson_id

    if report and report.get("pass"):
        current["status"] = "pass"
        plan[cursor] = current
        next_cursor = cursor + 1

        if next_cursor >= len(plan):
            nudge = SystemMessage(content=(
                "PLAN COMPLETE. Every lesson in the plan passed the critic.\n"
                "Phase → promoting. Now call draftSnapshot(thread_id) once to "
                "show the user the full outline, ask for confirmation, and then "
                "promote the accepted drafts to Supabase via the persistent "
                "createLesson/createChapter tools (or promoteDraftToSupabase "
                "if available). Do NOT author any more draft lessons.\n\n"
                "Plan recap:\n" + _plan_summary(plan, next_cursor)
            ))
            return {
                "plan": plan,
                "plan_cursor": next_cursor,
                "phase": "promoting",
                "messages": [nudge],
            }

        nxt = plan[next_cursor]
        nudge = SystemMessage(content=(
            f"STEP {cursor+1}/{len(plan)} PASSED ✅. Advancing the plan cursor.\n"
            f"Next step ({next_cursor+1}/{len(plan)}):\n"
            f"  Chapter : {nxt.get('chapter_title','?')}\n"
            f"  Lesson  : {nxt.get('lesson_title','?')}\n"
            f"  Brief   : {nxt.get('brief') or '(no extra brief — follow the user request)'}\n\n"
            "Author ONLY this lesson next. Use draftAddLesson under the right\n"
            "chapter, then batch content with draftAppendLessonContent until\n"
            "the critic passes. Do not jump ahead in the plan.\n\n"
            "Plan status:\n" + _plan_summary(plan, next_cursor)
        ))
        return {
            "plan": plan,
            "plan_cursor": next_cursor,
            "messages": [nudge],
        }

    if state.get("stop_reason") == "quality_gate_exhausted":
        current["status"] = "failed"
        plan[cursor] = current
        return {"plan": plan}

    current["status"] = "writing"
    plan[cursor] = current
    return {"plan": plan}


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
