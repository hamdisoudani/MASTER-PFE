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

# v2: the classic syllabus_agent now writes to Supabase via the persistent MCP
# tools. We keep the draft set around for subagents that still use the in-mem
# bucket (deep_graph's writer), but tools_post_hook treats persistent tools as
# the primary mutation surface and extracts Supabase IDs from their responses.
PERSISTENT_LESSON_MUTATION_TOOLS = LESSON_MUTATION_TOOLS

DRAFT_LESSON_MUTATION_TOOLS = {
    "draftAddLesson",
    "draftUpdateLessonContent",
    "draftAppendLessonContent",
    "draftPatchLessonBlocks",
}

# Union — any of these means "lesson blocks just changed, run the critic".
ALL_LESSON_MUTATION_TOOLS = LESSON_MUTATION_TOOLS | DRAFT_LESSON_MUTATION_TOOLS


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

        if tc["name"] in ALL_LESSON_MUTATION_TOOLS and not _was_user_rejected(resume_value):
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

    v2 responsibilities:
      1. ``submit_plan`` → register hierarchical plan:
            plan = [{title, summary, lessons:[{title, brief, ...}], ...}, ...]
         and flip phase → ``authoring``, stage → ``syllabus_create``,
         chapter_cursor=0, lesson_cursor=0.
      2. ``getOrCreateSyllabus`` → capture ``syllabus_id`` from the tool
         response, stage → ``chapter_propose``.
      3. ``addChapter`` → write chapter_id back to
         ``plan[chapter_cursor].chapter_id``, stage → ``lesson_outline``.
      4. ``addLesson`` → write lesson_id back to
         ``plan[chapter_cursor].lessons[lesson_cursor].lesson_id``,
         stage → ``lesson_content``. ALSO mirror its blocks into
         ``last_authored_lesson`` so the critic can evaluate them.
      5. ``appendLessonContent`` / ``updateLessonContent`` /
         ``patchLessonBlocks`` (persistent) and the ``draft*`` variants →
         mirror into ``last_authored_lesson`` for the critic.
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

    def _parse_result(tc_id: str) -> dict[str, Any] | None:
        tm = results_by_call_id.get(tc_id)
        if tm is None:
            return None
        try:
            parsed = json.loads(tm.content) if isinstance(tm.content, str) else None
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    update: dict[str, Any] = {}
    plan = [dict(c) for c in (state.get("plan") or [])]
    for c in plan:
        c["lessons"] = [dict(l) for l in (c.get("lessons") or [])]
    chapter_cursor = state.get("chapter_cursor")
    lesson_cursor = state.get("lesson_cursor")
    syllabus_id = state.get("syllabus_id")
    stage = state.get("stage")
    phase = state.get("phase") or "planning"

    # 1. submit_plan → build hierarchical plan
    for tc in (last_ai.tool_calls or []):
        if tc.get("name") != "submit_plan":
            continue
        args = tc.get("args") or {}
        chapters_in = args.get("chapters") or args.get("steps") or []
        normalized_plan: list[dict[str, Any]] = []
        for ch in chapters_in:
            if not isinstance(ch, dict):
                continue
            # Back-compat: a v1 flat step {chapter_title, lesson_title, brief}
            # becomes one chapter with one lesson.
            if "chapter_title" in ch and "lessons" not in ch:
                normalized_plan.append({
                    "title": str(ch.get("chapter_title") or "").strip(),
                    "summary": "",
                    "status": "pending",
                    "chapter_id": None,
                    "lessons": [{
                        "title": str(ch.get("lesson_title") or "").strip(),
                        "brief": str(ch.get("brief") or "").strip(),
                        "status": "pending",
                        "lesson_id": None,
                        "attempts": 0,
                    }],
                })
                continue
            lessons_norm = []
            for l in (ch.get("lessons") or []):
                if not isinstance(l, dict):
                    continue
                lessons_norm.append({
                    "title": str(l.get("title") or "").strip(),
                    "brief": str(l.get("brief") or "").strip(),
                    "status": "pending",
                    "lesson_id": None,
                    "attempts": 0,
                })
            normalized_plan.append({
                "title": str(ch.get("title") or "").strip(),
                "summary": str(ch.get("summary") or "").strip(),
                "status": "pending",
                "chapter_id": None,
                "lessons": lessons_norm,
            })
        if normalized_plan:
            plan = normalized_plan
            chapter_cursor = 0
            lesson_cursor = 0
            phase = "authoring"
            stage = "syllabus_create"
            logger.info("submit_plan (v2 nested): %d chapters, %d total lessons",
                        len(plan),
                        sum(len(c.get("lessons") or []) for c in plan))
        break

    # 2-4. Persistent tool result ingestion
    for tc in (last_ai.tool_calls or []):
        name = tc.get("name")
        args = tc.get("args") or {}
        if name == "getOrCreateSyllabus":
            res = _parse_result(tc.get("id")) or {}
            sid = res.get("id") or res.get("syllabus_id")
            if sid:
                syllabus_id = str(sid)
                if stage == "syllabus_create":
                    stage = "chapter_propose"
        elif name == "addChapter":
            res = _parse_result(tc.get("id")) or {}
            cid = res.get("id") or res.get("chapter_id")
            cc = chapter_cursor if chapter_cursor is not None else 0
            if cid and plan and 0 <= cc < len(plan):
                plan[cc]["chapter_id"] = str(cid)
                plan[cc]["status"] = "writing"
                if stage in (None, "chapter_propose", "chapter_commit"):
                    stage = "lesson_outline"
        elif name == "addLesson":
            res = _parse_result(tc.get("id")) or {}
            lid = res.get("id") or res.get("lesson_id")
            cc = chapter_cursor if chapter_cursor is not None else 0
            lc = lesson_cursor if lesson_cursor is not None else 0
            if lid and plan and 0 <= cc < len(plan):
                lessons = plan[cc].get("lessons") or []
                if 0 <= lc < len(lessons):
                    lessons[lc]["lesson_id"] = str(lid)
                    lessons[lc]["status"] = "content"
                if stage in (None, "lesson_outline", "lesson_create"):
                    stage = "lesson_content"

    # 5. mirror lesson-block mutations into last_authored_lesson (critic signal)
    last_mutation: dict[str, Any] | None = None
    for tc in (last_ai.tool_calls or []):
        name = tc.get("name")
        if name not in ALL_LESSON_MUTATION_TOOLS:
            continue
        args = tc.get("args") or {}
        if name in ("patchLessonBlocks", "draftPatchLessonBlocks"):
            blocks = args.get("patches") or args.get("blocks")
        elif name in ("appendLessonContent", "draftAppendLessonContent"):
            blocks = args.get("blocks")
        elif name in ("updateLessonContent", "draftUpdateLessonContent"):
            blocks = args.get("blocks")
        else:  # addLesson / draftAddLesson
            blocks = args.get("blocks") or args.get("content")
        blocks_list = blocks if isinstance(blocks, list) else []

        lesson_id = args.get("lesson_id") or args.get("lessonId") or args.get("chapter_id") or args.get("chapterId")
        if not lesson_id and name in ("addLesson", "draftAddLesson"):
            res = _parse_result(tc.get("id")) or {}
            lesson_id = res.get("id") or res.get("lesson_id")
        lesson_id = lesson_id or f"new:{(args.get('title') or '').strip() or 'unknown'}"

        last_mutation = {
            "lesson_id": str(lesson_id),
            "tool": name,
            "blocks": blocks_list,
            "title": args.get("title"),
        }

    if plan:
        update["plan"] = plan
    if chapter_cursor is not None:
        update["chapter_cursor"] = chapter_cursor
    if lesson_cursor is not None:
        update["lesson_cursor"] = lesson_cursor
    if syllabus_id is not None:
        update["syllabus_id"] = syllabus_id
    if stage is not None:
        update["stage"] = stage
    if phase:
        update["phase"] = phase
    if last_mutation is not None:
        update["last_authored_lesson"] = last_mutation

    return update


def route_after_python_tools(state: AgentState, config: RunnableConfig) -> str:
    """After the python/MCP tools + post-hook:

    - If a lesson mutation just happened, go to the critic (which then
      runs plan_router on its way back).
    - Else if we're in the hierarchical authoring phase, go directly to
      plan_router so the writer gets a next-stage nudge after
      ``getOrCreateSyllabus`` / ``addChapter`` / ``submit_plan`` returned.
    - Otherwise resume chat_node.
    """
    if state.get("last_authored_lesson"):
        return "critic_node"
    if (state.get("phase") or "planning") == "authoring":
        return "plan_router"
    return "chat_node"


def _plan_summary(plan: list[dict[str, Any]], cc: int, lc: int) -> str:
    if not plan:
        return ""
    lines = []
    for ci, ch in enumerate(plan):
        mark_c = "→" if ci == cc else " "
        lines.append(f"  {mark_c} Ch{ci+1}. ({ch.get('status','pending')}) "
                     f"{ch.get('title','?')}"
                     + (f"  [chapter_id={ch.get('chapter_id')}]" if ch.get("chapter_id") else ""))
        for li, l in enumerate(ch.get("lessons") or []):
            mark_l = "→" if (ci == cc and li == lc) else " "
            lines.append(f"      {mark_l} L{li+1}. ({l.get('status','pending')}) "
                         f"{l.get('title','?')}"
                         + (f"  [lesson_id={l.get('lesson_id')}]" if l.get("lesson_id") else ""))
    return "\n".join(lines)


def _nudge(stage: str, state_view: dict[str, Any]) -> str:
    """Build the SystemMessage that tells the writer exactly which persistent
    MCP tool to call next. Every nudge names the tool and the known IDs."""
    plan = state_view["plan"]
    cc = state_view["chapter_cursor"]
    lc = state_view["lesson_cursor"]
    sid = state_view.get("syllabus_id")
    ch = plan[cc] if 0 <= cc < len(plan) else {}
    lessons = ch.get("lessons") or []
    lsn = lessons[lc] if 0 <= lc < len(lessons) else {}

    if stage == "syllabus_create":
        return (
            "AUTHORING PHASE · stage = syllabus_create.\n"
            "Call the persistent MCP tool getOrCreateSyllabus(thread_id, title) "
            "exactly once to materialize the syllabus in Supabase. "
            "Use the user-agreed title from the plan. "
            "Do NOT call any draft* tools from now on."
        )
    if stage == "chapter_propose":
        return (
            f"AUTHORING PHASE · stage = chapter_propose.\n"
            f"Syllabus id: {sid}\n"
            f"Next chapter ({cc+1}/{len(plan)}):\n"
            f"  title  : {ch.get('title','?')}\n"
            f"  summary: {ch.get('summary','(none)')}\n\n"
            "Call addChapter(syllabus_id, title, summary, position) now. "
            "No free-text turn — emit the tool call directly."
        )
    if stage == "lesson_outline":
        return (
            f"AUTHORING PHASE · stage = lesson_outline.\n"
            f"Chapter id: {ch.get('chapter_id')}  ({ch.get('title','?')})\n"
            f"Next lesson ({lc+1}/{len(lessons)}): {lsn.get('title','?')}\n"
            f"Brief: {lsn.get('brief') or '(follow chapter summary)'}\n\n"
            "Call addLesson(chapter_id, title, blocks=[…scaffold blocks: H2 sections "
            "'Learning objectives','Lesson','Worked example','Practice','Summary','Sources'…]). "
            "One tool call, no prose."
        )
    if stage == "lesson_content":
        return (
            f"AUTHORING PHASE · stage = lesson_content.\n"
            f"Lesson id: {lsn.get('lesson_id')}  ({lsn.get('title','?')})\n"
            f"Brief: {lsn.get('brief') or '(follow chapter summary)'}\n\n"
            "Use appendLessonContent(lesson_id, blocks=[…]) to fill the body. "
            "Batch 2–3 append calls until the critic passes. "
            "Do NOT create another lesson; the graph will advance when the "
            "critic passes this one."
        )
    if stage == "done":
        return "All chapters and lessons committed to Supabase. Summarize for the user and stop."
    return ""


def plan_router(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Hierarchical v2 advancement after each critic verdict.

    Only runs during phase=='authoring'. Advances (chapter_cursor, lesson_cursor)
    and flips `stage` through: syllabus_create → chapter_propose → lesson_outline
    → lesson_content → (next lesson | next chapter | done). Emits a SystemMessage
    that names the exact persistent MCP tool the writer should call next.
    """
    phase = state.get("phase") or "planning"
    plan = [dict(c) for c in (state.get("plan") or [])]
    for c in plan:
        c["lessons"] = [dict(l) for l in (c.get("lessons") or [])]

    if phase != "authoring" or not plan:
        return {}

    cc = int(state.get("chapter_cursor") or 0)
    lc = int(state.get("lesson_cursor") or 0)
    cc = max(0, min(cc, len(plan) - 1))
    stage = state.get("stage") or "syllabus_create"

    reports = state.get("critic_reports") or {}
    last = state.get("last_authored_lesson") or {}
    lesson_id = last.get("lesson_id")
    report = reports.get(lesson_id) if lesson_id else None

    # --- lesson_content: advance only after critic PASS
    if stage == "lesson_content" and report and report.get("pass"):
        lessons = plan[cc].get("lessons") or []
        if 0 <= lc < len(lessons):
            lessons[lc]["status"] = "done"
        # next lesson in same chapter?
        if lc + 1 < len(lessons):
            lc += 1
            stage = "lesson_outline"
        else:
            plan[cc]["status"] = "done"
            if cc + 1 < len(plan):
                cc += 1
                lc = 0
                stage = "chapter_propose"
            else:
                stage = "done"
                phase_out = "done"
                nudge = SystemMessage(content=_nudge("done", {
                    "plan": plan, "chapter_cursor": cc, "lesson_cursor": lc,
                    "syllabus_id": state.get("syllabus_id"),
                }) + "\n\nPlan recap:\n" + _plan_summary(plan, cc, lc))
                return {
                    "plan": plan, "chapter_cursor": cc, "lesson_cursor": lc,
                    "stage": stage, "phase": phase_out, "messages": [nudge],
                    "stop_reason": "completed",
                }
        nudge = SystemMessage(content=_nudge(stage, {
            "plan": plan, "chapter_cursor": cc, "lesson_cursor": lc,
            "syllabus_id": state.get("syllabus_id"),
        }) + "\n\nPlan status:\n" + _plan_summary(plan, cc, lc))
        return {
            "plan": plan, "chapter_cursor": cc, "lesson_cursor": lc,
            "stage": stage, "messages": [nudge],
        }

    # --- critic exhausted revision budget on this lesson → mark failed, stop
    if state.get("stop_reason") == "quality_gate_exhausted":
        lessons = plan[cc].get("lessons") or []
        if 0 <= lc < len(lessons):
            lessons[lc]["status"] = "failed"
        return {"plan": plan}

    # --- otherwise: fresh stage transitions are handled by tools_post_hook
    #     when the persistent tool result comes back. We just re-issue the
    #     nudge for the current stage so the writer knows what to call next.
    nudge = SystemMessage(content=_nudge(stage, {
        "plan": plan, "chapter_cursor": cc, "lesson_cursor": lc,
        "syllabus_id": state.get("syllabus_id"),
    }))
    return {"messages": [nudge] if nudge.content else []}


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
