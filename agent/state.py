from __future__ import annotations
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Syllabus agent state.

    Additions vs. pure ReAct:
    - `research_cache`: per-lesson/per-topic store of scraped sources so the
      writer can ground content without hydrating chat history on every turn.
      Shape: {lesson_id | topic_key: [{"url","title","markdown","query"}]}.
    - `critic_reports`: latest rubric verdict per lesson (pass/fail + reasons).
    - `revision_attempts`: per-lesson revision counter (capped to avoid loops).
    - `last_authored_lesson`: the lesson id/title most recently created or
      patched — used by the critic node to pick its target.
    - `stop_reason`: terminal status chip for the UI.
    """

    messages: Annotated[list, add_messages]
    editor_context: Optional[dict[str, Any]]
    stop_reason: Optional[str]

    research_cache: Optional[dict[str, list[dict[str, Any]]]]
    critic_reports: Optional[dict[str, dict[str, Any]]]
    revision_attempts: Optional[dict[str, int]]
    last_authored_lesson: Optional[dict[str, Any]]
    # Per-lessonId accumulator of blocks across addLesson + appendLessonContent
    # batches, so the critic evaluates the aggregate lesson, not each batch.
    lesson_blocks_cache: Optional[dict[str, list[dict[str, Any]]]]
    # Context-window meter: {tokens, budget, fraction} updated each chat_node
    # call so the UI can render an agent context-usage gauge.
    context_usage: Optional[dict[str, Any]]
    # Deterministic plan state machine for syllabus_agent.
    # `plan` is the ordered list of lessons the writer must author, each
    # with {chapter_title, lesson_title, brief, status, attempts,
    # draft_lesson_id}. `plan_cursor` is the index of the step currently
    # being worked on. `phase` is "planning" (ReAct with the user to
    # build a plan), "writing" (strict plan-driven authoring loop), or
    # "promoting" (copy the accepted drafts to Supabase via the
    # frontend mutation tools). The graph uses these fields to route
    # after the critic, instead of relying on the LLM to choose nodes.
    plan: Optional[list[dict[str, Any]]]
    plan_cursor: Optional[int]
    phase: Optional[str]
    # --- v2 hierarchical authoring (syllabus_agent) ---
    # `plan` is now CHAPTER-level: each chapter has nested lessons. The graph
    # drives (chapter_cursor, lesson_cursor) deterministically, and writes
    # Supabase IDs back into the plan as the agent commits each entity.
    #
    # plan: [
    #   {
    #     "title": str, "summary": str, "status": pending|writing|done|failed,
    #     "chapter_id": Optional[str],   # filled after addChapter
    #     "lessons": [
    #        {
    #          "title": str, "brief": str,
    #          "status": pending|outline|content|done|failed,
    #          "lesson_id": Optional[str],    # filled after addLesson
    #          "attempts": int,
    #        }, ...
    #     ],
    #   }, ...
    # ]
    chapter_cursor: Optional[int]
    lesson_cursor: Optional[int]
    syllabus_id: Optional[str]
    # Fine-grained stage within `phase="authoring"` — lets the SystemMessage
    # nudges be specific about which persistent tool to call next.
    stage: Optional[str]
