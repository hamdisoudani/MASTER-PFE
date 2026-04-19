"""Deep-agent variant of the MASTER-PFE syllabus agent.

Wraps Mistral with `deepagents.create_deep_agent`, which adds planning
(`write_todos`), a virtual filesystem, and three specialized subagents
(researcher, writer, reviser). Our python tools + static frontend-tool
shells are passed through so the agent can both research the web and
emit editor mutations as LangGraph interrupts — exactly like the classic
graph does.

Registered in `langgraph.json` as `syllabus_agent_deep`. The frontend
picks the assistant id at thread creation and stores it in thread
metadata (`variant: "classic" | "deep"`); once chosen it cannot change
for that thread.
"""
from __future__ import annotations
import logging

from deepagents import create_deep_agent
from deepagents.middleware.subagents import SubAgent

from agent.checkpointer import get_checkpointer
from agent.frontend_shells import (
    FRONTEND_SHELL_TOOLS,
    addLesson,
    appendLessonContent,
    patchLessonBlocks,
)
from agent.llm import get_llm
from agent.tools import PYTHON_TOOLS, web_search, scrape_page

logger = logging.getLogger(__name__)


DEEP_SYSTEM_PROMPT = """You are MASTER-PFE's deep curriculum agent — a senior
instructional designer operating BlockNote documents for real learners
(often children/students).

You plan explicitly with `write_todos`, delegate research to the `researcher`
subagent, drafting to `writer`, and revision to `reviser`.

WORKFLOW
1. For any course/chapter with more than one lesson, call `write_todos`
   FIRST with one todo per lesson.
2. For each lesson:
   a. delegate research to `researcher` (returns compact notes),
   b. delegate drafting to `writer` (calls addLesson / appendLessonContent /
      patchLessonBlocks — the user confirms via the editor UI),
   c. if the user asks for fixes or reports quality issues, delegate to
      `reviser` (hard cap: 2 revision rounds per lesson).
3. Mark the todo complete. Move to the next lesson.

HARD RULES (identical to classic agent)
- NEVER use ellipses or 'etc.' to skip items in an enumeration. List every
  number, letter, or word in a sequence.
- Every lesson must have >= 18 BlockNote blocks and the canonical H2
  skeleton: Learning Objectives, Lesson, Worked Example, Practice, Summary,
  Sources.
- Never write meta-commentary like 'Here is the lesson'. Write the lesson.
- Ground content in real scraped sources; cite them under Sources.

You run on Mistral. Keep your own messages short; do the writing work
inside subagent calls so their output lands directly in the editor via
frontend tool calls."""


RESEARCHER_PROMPT = """You are the researcher subagent.
Use `web_search` to find 2-4 authoritative sources for the topic, then
`scrape_page` each one. Return a compact notes document (<=1500 tokens)
with: one paragraph per source summarizing parts relevant to the lesson,
plus a bullet list of concrete facts/examples with the source URL on each.
Do not write the lesson — only notes the writer can draft from."""


WRITER_PROMPT = """You are the writer subagent. Given a lesson spec and
research notes, produce the lesson by calling ONE of addLesson,
appendLessonContent, or patchLessonBlocks.

Canonical H2 skeleton (required):
  1. Learning Objectives (3-5 bullets)
  2. Lesson (main explanation with subheadings and examples)
  3. Worked Example (one fully solved example, step by step)
  4. Practice (3-6 exercises with answers)
  5. Summary (bullet recap)
  6. Sources (real URLs from research)

Minimum 18 blocks. List every item in a sequence - no ellipses. After the
tool call, stop; do not narrate."""


REVISER_PROMPT = """You are the reviser subagent. You receive the current
lesson blocks and a list of issues (missing sections, too few blocks, low
block-type variety, forbidden ellipses, etc.). Call `patchLessonBlocks`
with a surgical patch that fixes EVERY listed issue while preserving the
correct parts. Never shrink the lesson; add the missing sections/blocks."""


SUBAGENTS: list[SubAgent] = [
    {
        "name": "researcher",
        "description": "Finds and summarizes authoritative web sources for a lesson topic.",
        "system_prompt": RESEARCHER_PROMPT,
        "tools": [web_search, scrape_page],
    },
    {
        "name": "writer",
        "description": "Drafts a full lesson and writes it to the editor via a frontend tool call.",
        "system_prompt": WRITER_PROMPT,
        "tools": [addLesson, appendLessonContent, patchLessonBlocks],
    },
    {
        "name": "reviser",
        "description": "Applies critic feedback by patching specific lesson blocks.",
        "system_prompt": REVISER_PROMPT,
        "tools": [patchLessonBlocks],
    },
]


def build_graph():
    all_tools = list(PYTHON_TOOLS) + list(FRONTEND_SHELL_TOOLS)
    agent = create_deep_agent(
        model=get_llm(),
        tools=all_tools,
        system_prompt=DEEP_SYSTEM_PROMPT,
        subagents=SUBAGENTS,
        checkpointer=get_checkpointer(),
    )
    return agent


graph = build_graph()
