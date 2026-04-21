from __future__ import annotations
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Syllabus agent state.

    Three channels (see design doc / checkpoint notes):

    UI-visible channel:
      - ``messages`` — ONLY publisher / user / assistant content. Anything
        that writes here is rendered in the chat pane. Internal nodes must
        NOT append SystemMessages or critic prose here. Residual internal
        notes that *must* flow through ``messages`` (e.g. for LangGraph
        wiring reasons) must carry ``additional_kwargs={"internal": True}``
        so the frontend filter (``hiddenMessageIds``) drops them.

    Internal channel (never rendered):
      - ``critic_feedback`` — free-form fix instructions injected into the
        fresh system prompt by ``chat_node`` on the next turn, then cleared.
      - ``critique`` — structured dict ``{lesson_id, issues, stats, score}``
        from the deterministic rubric. Replaces the old SystemMessage
        leak. Consumed by ``chat_node`` (via ``critic_feedback``) and by
        tests/telemetry.
      - ``revision_attempts`` — per-lesson counter, capped by
        ``CRITIC_MAX_REVISIONS``.
      - ``critic_reports`` — latest rubric verdict per lesson (history).
      - ``last_authored_lesson`` — handoff from ``frontend_tool_node`` to
        ``critic_node`` for which lesson to evaluate. Cleared by critic.
      - ``lesson_blocks_cache`` — aggregated blocks across batched mutations.
      - ``research_cache`` — scraped sources keyed by topic/lesson.
      - ``draft_ref`` — MCP draft pointer (reserved for the writer↔critic
        MCP-draft lifecycle follow-up; unused in the current graph).

    Meta:
      - ``editor_context`` — cursor / selection info from the browser editor.
      - ``stop_reason`` — terminal classifier (``completed``,
        ``interrupted_by_user``, ``quality_gate_exhausted``, ``error``).
      - ``context_usage`` — {tokens, budget, fraction} for the UI meter.
      - ``draft_syllabus_id`` — id of the MCP draft syllabus.
      - ``publish_status`` — compact chip data after a promote.
      - ``gc_stats`` — debug counters from ``gc_state``.
    """

    messages: Annotated[list, add_messages]
    editor_context: Optional[dict[str, Any]]
    stop_reason: Optional[str]

    # Internal (non-UI) channels — see module docstring.
    critic_feedback: Optional[str]
    critique: Optional[dict[str, Any]]
    critic_reports: Optional[dict[str, dict[str, Any]]]
    revision_attempts: Optional[dict[str, int]]
    last_authored_lesson: Optional[dict[str, Any]]
    lesson_blocks_cache: Optional[dict[str, list[dict[str, Any]]]]
    research_cache: Optional[dict[str, list[dict[str, Any]]]]
    draft_ref: Optional[str]

    context_usage: Optional[dict[str, Any]]
    draft_syllabus_id: Optional[str]
    publish_status: Optional[dict[str, Any]]
    gc_stats: Optional[dict[str, Any]]
