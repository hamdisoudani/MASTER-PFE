"""Agent middleware — context control + robustness.

Applied via `chat_node` before each LLM invocation and around tool execution.
Ported in spirit from langchain-ai/open-swe's middleware stack:
- SummarizationMiddleware equivalent → compact_history()
- ToolErrorMiddleware → safe_tool_invoke()
- ensure_no_empty_msg → handle_empty_ai_response()
- tool-arg/result elision → compact_tool_history()
"""
from __future__ import annotations
import json
import logging
from typing import Any, Iterable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

KEEP_RECENT_TURNS = 6
MAX_TOOL_RESULT_CHARS = 1200
MAX_ELIDED_TOOL_RESULT_CHARS = 400
ELIDABLE_MUTATION_TOOLS = {
    "addLesson",
    "updateLessonContent",
    "appendLessonContent",
    "patchLessonBlocks",
}
ELIDABLE_READ_TOOLS = {"scrape_page", "web_search", "getSyllabusOutline", "readLessonBlocks"}


def _approx_tokens(messages: Iterable[BaseMessage]) -> int:
    """Cheap proxy for token count (chars/4). Avoids a tokenizer dependency."""
    total = 0
    for m in messages:
        c = m.content
        if isinstance(c, str):
            total += len(c)
        else:
            try:
                total += len(json.dumps(c))
            except Exception:
                total += len(str(c))
        tcs = getattr(m, "tool_calls", None) or []
        for tc in tcs:
            try:
                total += len(json.dumps(tc.get("args") or {}))
            except Exception:
                total += 200
    return total // 4


def _boundary_indices(messages: list[BaseMessage]) -> list[int]:
    """Return indices of safe conversation boundaries (HumanMessage starts).

    A boundary is safe because no tool-call/tool-result bond crosses it —
    we only split where the previous AIMessage had all its ToolMessages
    already emitted.
    """
    idxs = []
    pending: set[str] = set()
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage):
            pending = {tc.get("id") for tc in (getattr(m, "tool_calls", None) or []) if tc.get("id")}
        elif isinstance(m, ToolMessage):
            pending.discard(getattr(m, "tool_call_id", None))
        elif isinstance(m, HumanMessage) and not pending:
            idxs.append(i)
    return idxs


def _summarize_slice(slice_msgs: list[BaseMessage]) -> str:
    """Deterministic, cheap summary — no extra LLM call.

    We include: the first user ask, tool names invoked, final AI gist.
    For long-running agents this is enough to preserve intent without
    re-sending full tool arg blobs.
    """
    bullets: list[str] = []
    first_user = next((m for m in slice_msgs if isinstance(m, HumanMessage)), None)
    if first_user:
        t = str(first_user.content)[:300].replace("\n", " ")
        bullets.append(f"- User asked: {t}")
    tool_counts: dict[str, int] = {}
    for m in slice_msgs:
        if isinstance(m, AIMessage):
            for tc in (getattr(m, "tool_calls", None) or []):
                n = tc.get("name") or "?"
                tool_counts[n] = tool_counts.get(n, 0) + 1
    if tool_counts:
        parts = ", ".join(f"{k}×{v}" for k, v in sorted(tool_counts.items(), key=lambda x: -x[1]))
        bullets.append(f"- Tools used in this window: {parts}")
    final_ai = next(
        (m for m in reversed(slice_msgs) if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip()),
        None,
    )
    if final_ai:
        t = str(final_ai.content)[:400].replace("\n", " ")
        bullets.append(f"- Last assistant note: {t}")
    return "Conversation summary (earlier window elided to control context size):\n" + "\n".join(bullets)


def _elide_tool_args(ai: AIMessage) -> AIMessage:
    """Replace bulky `content`/`blocks` arrays inside resolved mutation tool_calls."""
    tcs = list(getattr(ai, "tool_calls", None) or [])
    if not tcs:
        return ai
    changed = False
    new_tcs = []
    for tc in tcs:
        name = tc.get("name")
        args = tc.get("args") or {}
        if name in ELIDABLE_MUTATION_TOOLS and isinstance(args, dict):
            new_args = dict(args)
            for k in ("content", "blocks"):
                v = new_args.get(k)
                if isinstance(v, list) and len(v) > 0:
                    new_args[k] = [{"__elided__": True, "blockCount": len(v)}]
                    changed = True
            tc = {**tc, "args": new_args}
        new_tcs.append(tc)
    if not changed:
        return ai
    return AIMessage(
        content=ai.content,
        tool_calls=new_tcs,
        additional_kwargs=getattr(ai, "additional_kwargs", {}) or {},
        id=getattr(ai, "id", None),
    )


def _elide_tool_result(tm: ToolMessage, name_hint: str | None) -> ToolMessage:
    content = tm.content if isinstance(tm.content, str) else json.dumps(tm.content, default=str)
    if len(content) <= MAX_TOOL_RESULT_CHARS:
        return tm
    head = content[:MAX_ELIDED_TOOL_RESULT_CHARS]
    return ToolMessage(
        content=head + f"\n…[elided {len(content) - len(head)} chars from {name_hint or 'tool result'}]",
        tool_call_id=tm.tool_call_id,
        status=getattr(tm, "status", None),
    )


def compact_tool_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Rewrite messages OUTSIDE the recent window:

    - elide bulky addLesson/updateLessonContent args to a stub
    - truncate large scrape_page / web_search tool results
    The most recent KEEP_RECENT_TURNS HumanMessage boundaries are preserved verbatim.
    """
    if not messages:
        return messages
    boundaries = _boundary_indices(messages)
    if len(boundaries) <= KEEP_RECENT_TURNS:
        recent_start = 0
    else:
        recent_start = boundaries[-KEEP_RECENT_TURNS]
    out: list[BaseMessage] = []
    tool_name_by_id: dict[str, str] = {}
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage):
            for tc in (getattr(m, "tool_calls", None) or []):
                if tc.get("id") and tc.get("name"):
                    tool_name_by_id[tc["id"]] = tc["name"]
        if i >= recent_start:
            out.append(m)
            continue
        if isinstance(m, AIMessage):
            out.append(_elide_tool_args(m))
        elif isinstance(m, ToolMessage):
            hint = tool_name_by_id.get(getattr(m, "tool_call_id", ""))
            if hint in ELIDABLE_READ_TOOLS or hint is None:
                out.append(_elide_tool_result(m, hint))
            else:
                out.append(m)
        else:
            out.append(m)
    return out


def compact_history(messages: list[BaseMessage], token_budget: int = 12000) -> list[BaseMessage]:
    """If the conversation is over budget, summarize the earliest safe window.

    Safe = does not break any tool_call ↔ ToolMessage bond.
    """
    if not messages:
        return messages
    messages = compact_tool_history(messages)
    if _approx_tokens(messages) <= token_budget:
        return messages

    boundaries = _boundary_indices(messages)
    if len(boundaries) < 2:
        return messages

    keep_from = boundaries[-KEEP_RECENT_TURNS] if len(boundaries) > KEEP_RECENT_TURNS else boundaries[len(boundaries) // 2]
    older = messages[:keep_from]
    recent = messages[keep_from:]
    if not older:
        return messages

    summary = _summarize_slice(older)
    compacted: list[BaseMessage] = [SystemMessage(content=summary)] + recent
    logger.info(
        "compact_history: compressed %d→%d messages (≈%d→%d tokens)",
        len(messages), len(compacted), _approx_tokens(messages), _approx_tokens(compacted),
    )
    return compacted


def ensure_no_empty_ai(messages: list[BaseMessage]) -> list[BaseMessage]:
    """If the latest AIMessage is empty and has no tool calls, nudge the model once."""
    if not messages:
        return messages
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return messages
    tcs = getattr(last, "tool_calls", None) or []
    content = last.content
    if tcs:
        return messages
    txt = content if isinstance(content, str) else ""
    if txt.strip():
        return messages
    return messages + [SystemMessage(
        content=(
            "You produced an empty response and no tool call. "
            "Either call the appropriate tool now, or tell the user concisely what you need."
        )
    )]


def safe_tool_exception(exc: BaseException, tool_call_id: str) -> ToolMessage:
    """Standard error ToolMessage shape — ported from open-swe's ToolErrorMiddleware."""
    return ToolMessage(
        content=json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
        tool_call_id=tool_call_id,
        status="error",
    )


def normalize_system_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Provider-agnostic: keep system messages ONLY at index 0.

    Any SystemMessage at index > 0 (e.g. critic feedback, user-rejection
    nudges, compact_history summary injected mid-stream) is rewritten as
    a HumanMessage tagged "[system-note] ..." so providers like Mistral
    that require "System message must be at the beginning" stop rejecting
    the conversation. Leading SystemMessages are left alone; chat_node
    will prepend the real system prompt on top.
    """
    if not messages:
        return messages
    out: list[BaseMessage] = []
    for i, m in enumerate(messages):
        if isinstance(m, SystemMessage) and i != 0:
            text = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
            out.append(HumanMessage(content="[system-note] " + text))
        else:
            out.append(m)
    return out
