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


SUMMARY_PROMPT = (
    "You are a conversation compaction tool for a multi-agent curriculum "
    "authoring system (MASTER-PFE). Summarize the earlier portion of the "
    "conversation below so a downstream LLM can continue the work WITHOUT "
    "seeing the original messages. Be faithful and concrete.\n\n"
    "Required sections (use exactly these headings):\n"
    "### User intent\n"
    "### Lessons & artifacts produced so far (ids, titles, status)\n"
    "### Tools used and key results (names, counts, salient URLs/ids)\n"
    "### Open issues / pending todos\n"
    "### Decisions & constraints to preserve\n\n"
    "Rules:\n"
    "- Preserve EVERY lessonId, URL, and numeric fact that may be needed later.\n"
    "- Do NOT invent facts. If unsure, say 'unclear'.\n"
    "- Target 250-500 words. Plain text, no code fences."
)


def _deterministic_summary(slice_msgs: list[BaseMessage]) -> str:
    """Fallback summary when the LLM call is unavailable (no key, network error)."""
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
    return (
        "Conversation summary (deterministic fallback — LLM summarizer "
        "unavailable):\n" + "\n".join(bullets)
    )


def _render_slice_for_llm(slice_msgs: list[BaseMessage], char_budget: int = 48000) -> str:
    """Render the slice as a compact transcript the summarizer LLM can read.

    Elides tool args/results first so we don't feed 500kB of scraped HTML into
    the summarization prompt, and hard-truncates at ``char_budget``.
    """
    elided = compact_tool_history(list(slice_msgs))
    lines: list[str] = []
    for m in elided:
        if isinstance(m, HumanMessage):
            role = "USER"
            body = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
        elif isinstance(m, AIMessage):
            role = "ASSISTANT"
            body = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
            tcs = getattr(m, "tool_calls", None) or []
            if tcs:
                names = ", ".join(f"{tc.get('name')}({', '.join((tc.get('args') or {}).keys())})" for tc in tcs)
                body = (body + "\n" if body else "") + f"[tool_calls: {names}]"
        elif isinstance(m, ToolMessage):
            role = f"TOOL({getattr(m, 'name', None) or 'result'})"
            body = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
        elif isinstance(m, SystemMessage):
            role = "SYSTEM"
            body = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
        else:
            continue
        if not isinstance(body, str):
            body = str(body)
        body = body.strip()
        if not body:
            continue
        lines.append(f"[{role}] {body}")
    text = "\n\n".join(lines)
    if len(text) > char_budget:
        head = text[: char_budget // 2]
        tail = text[-char_budget // 2 :]
        text = head + f"\n\n…[{len(text) - char_budget} chars elided from middle]…\n\n" + tail
    return text


def _summarize_slice(slice_msgs: list[BaseMessage]) -> str:
    """LLM-backed summary, with deterministic fallback on any failure.

    We call the same LLM the agent uses (``agent.llm.get_llm``) at low temp
    with a compact transcript of the older window. This mirrors what the
    deep-graph ``SummarizationMiddleware`` does for the deep agent.
    """
    if not slice_msgs:
        return ""
    try:
        from agent.llm import get_llm  # local import to avoid circular import at module load
        llm = get_llm()
        transcript = _render_slice_for_llm(slice_msgs)
        resp = llm.invoke([
            SystemMessage(content=SUMMARY_PROMPT),
            HumanMessage(content=transcript),
        ])
        text = resp.content if isinstance(resp.content, str) else json.dumps(resp.content, default=str)
        text = (text or "").strip()
        if len(text) < 40:
            raise RuntimeError("summary too short")
        logger.info("compact_history: LLM summary produced (%d chars)", len(text))
        return "Conversation summary (LLM-generated):\n" + text
    except Exception as e:  # noqa: BLE001
        logger.warning("compact_history: LLM summary failed (%s) — falling back to deterministic", e)
        return _deterministic_summary(slice_msgs)


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
    compacted: list[BaseMessage] = [HumanMessage(content="[compact-summary] " + summary, additional_kwargs={"internal": True, "kind": "compact-summary"})] + recent
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
    """Provider-agnostic: strip ALL SystemMessages from thread history.

    ``chat_node`` always prepends a fresh, authoritative SystemMessage
    (``build_system_prompt``) at position 0 before calling the LLM. Any
    SystemMessage that lives inside the persisted thread — critic feedback,
    user-rejection nudges, compact_history summaries injected mid-stream, or
    a SystemMessage accidentally saved at index 0 from a previous turn —
    would push to index 1+ of the final payload and trip providers (Mistral,
    GPT-5, Claude on Bedrock) with "System message must be at the beginning."

    We rewrite EVERY SystemMessage in the thread as a
    ``HumanMessage("[system-note] ...")`` so the information is preserved
    verbatim and the model still sees it, while never violating the
    provider invariant.
    """
    if not messages:
        return messages
    out: list[BaseMessage] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            text = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
            out.append(HumanMessage(content="[system-note] " + text, additional_kwargs={"internal": True, "kind": "system-note"}))
        else:
            out.append(m)
    return out


def estimate_context_usage(messages: Iterable[BaseMessage], budget: int) -> dict:
    """Return {tokens, budget, fraction} for the agent UI context-window meter."""
    tok = _approx_tokens(messages)
    frac = 0.0 if budget <= 0 else min(1.0, tok / float(budget))
    return {"tokens": int(tok), "budget": int(budget), "fraction": round(frac, 4)}
