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
