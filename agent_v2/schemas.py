"""Pydantic schemas for forced structured output."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal


class SubStepSchema(BaseModel):
    id: str
    kind: Literal["lesson", "activity"]
    title: str
    goals: list[str] = Field(default_factory=list, description="Concrete points this lesson/activity must cover (used by critic as rubric).")


class ChapterSchema(BaseModel):
    id: str
    title: str
    summary: str = ""
    substeps: list[SubStepSchema]


class PlanSchema(BaseModel):
    topic: str
    audience: str
    language: str = "en"
    chapters: list[ChapterSchema]


class LessonDraftSchema(BaseModel):
    title: str
    blocks: list[dict] = Field(description="BlockNote-compatible block array.")


class ActivityDraftSchema(BaseModel):
    question: str
    options: list[str] = Field(min_length=2, max_length=6)
    multi: bool = False
    correct_index: int | list[int] = Field(description="Index (or list of indices for multi) of correct option(s) in `options`.")
    explanation: str = ""


class CriticSchema(BaseModel):
    passed: bool = Field(description="True iff the draft meets EVERY goal of the current substep.")
    issues: list[str] = Field(default_factory=list, description="Concrete missing or incorrect points. Empty iff passed=True.")
    score: float = 0.0


class ResearchRecommendationSchema(BaseModel):
    suggested_topic: str
    suggested_audience: str
    suggested_language: str = "en"
    recommended_chapter_titles: list[str]
    notes: list[str] = Field(default_factory=list, description="Grounding facts used to seed chapter `covers` / `goals` later.")
