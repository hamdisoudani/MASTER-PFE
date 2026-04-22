"""State for agent_v2.

Design goals:
- UI channel (`messages`) is minimal: only user/assistant chat turns. Writer<->critic
  exchanges happen entirely in `current_draft` / `current_critic`, never in messages.
- Plan is deterministic: a list of Chapter steps, each with lesson/activity substeps.
  A static router advances through them. LLM cannot decide which step is next.
- Per substep loop writes to transient fields which are cleared once the substep is
  marked done, so the checkpoint does not grow unboundedly.
"""
from __future__ import annotations
from typing import Annotated, Any, Literal, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


SubStepKind = Literal["lesson", "activity"]


class SubStep(TypedDict, total=False):
    id: str
    kind: SubStepKind
    title: str
    goals: list[str]            # bullet points the critic uses as rubric
    covers: list[str]           # grounding notes from web research
    done: bool
    persisted_id: Optional[str] # supabase id of the lesson/activity row once written


class ChapterStep(TypedDict, total=False):
    id: str
    title: str
    summary: str
    substeps: list[SubStep]
    done: bool


class Plan(TypedDict, total=False):
    topic: str
    audience: str
    language: str
    chapters: list[ChapterStep]


class LessonDraft(TypedDict, total=False):
    title: str
    blocks: list[dict[str, Any]]  # BlockNote-compatible block array
    substep_id: str


class ActivityDraft(TypedDict, total=False):
    question: str
    options: list[str]
    correct_index: int | list[int]
    multi: bool
    explanation: str
    substep_id: str


class CriticReport(TypedDict, total=False):
    pass_: bool                 # typed as `pass_` because `pass` is reserved
    issues: list[str]
    score: float


class AgentStateV2(TypedDict, total=False):
    # UI-visible
    messages: Annotated[list, add_messages]

    # Gathered profile (from info_gather / askUser)
    profile: dict[str, Any]

    # Internal, transient web research — cleared at end of info_gather
    research_cache: list[dict[str, Any]]

    # Plan with chapters/substeps + their goals/covers
    plan: Optional[Plan]
    current_chapter_idx: int
    current_substep_idx: int

    # Writer<->critic loop — state only, not messages
    current_draft: Optional[dict[str, Any]]   # LessonDraft or ActivityDraft
    current_critic: Optional[CriticReport]
    current_attempts: int

    # Meta
    stop_reason: Optional[str]
    draft_syllabus_id: Optional[str]
