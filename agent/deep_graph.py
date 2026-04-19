"""Deep-agent variant of the MASTER-PFE syllabus agent.

Architecture (aligned with deepagents design):

  supervisor (orchestrator ONLY)
    |  tools: write_todos (from TodoListMiddleware), task (from SubAgentMiddleware),
    |         setPlan / updatePlanItem (to surface progress in the editor UI).
    |  NO web tools. NO lesson mutations. The supervisor must NOT do the
    |  work itself - it decomposes, plans, delegates, and checks.
    |
    +-- researcher   tools: web_search, scrape_page
    +-- writer       tools: addLesson, updateLessonContent, appendLessonContent
    +-- reviser      tools: patchLessonBlocks

Critical deepagents semantics we design around:
  * task(description, subagent_type) creates a fresh subagent with a
    SINGLE HumanMessage equal to `description`. Subagents do NOT inherit
    the supervisor's chat history. They start BLIND.
  * Therefore the supervisor MUST pack every bit of context the subagent
    needs (topic, audience, constraints, prior research notes, target
    lesson id, concrete issue list, etc.) into that description string.
  * Each subagent has its own middleware stack (todo list, filesystem,
    summarization) which deepagents installs automatically, plus ONLY
    the tools we declare - so subagents cannot reach outside their role.

Registered in `langgraph.json` as `syllabus_agent_deep`. The frontend
picks the variant at thread creation and stores it in thread metadata
(`variant: "classic" | "deep"`); once chosen it cannot change.
"""
from __future__ import annotations
import logging

from deepagents import create_deep_agent
from deepagents.middleware.subagents import SubAgent

from agent.checkpointer import get_checkpointer
from agent.frontend_shells import (
    addLesson,
    updateLessonContent,
    appendLessonContent,
    patchLessonBlocks,
    setPlan,
    updatePlanItem,
)
from agent.llm import get_llm
from agent.tools import web_search, scrape_page

logger = logging.getLogger(__name__)


SUPERVISOR_PROMPT = """You are MASTER-PFE's deep curriculum SUPERVISOR.
You are an orchestrator, not a writer. You do NOT call web tools and you
do NOT call lesson-mutation tools yourself - those belong to your
subagents.

You operate BlockNote lessons for real learners (often children/students).

## Tools available to YOU (supervisor)
- write_todos     - plan the full job up front; one todo per lesson.
- task            - delegate to a subagent (researcher, writer, reviser).
                    This is how real work gets done.
- setPlan         - publish the plan to the editor UI so the user sees it.
- updatePlanItem  - flip a plan item to in_progress / done as you go.

## Subagents (each starts BLIND - no chat history, no memory of prior turns)
- researcher  tools: web_search, scrape_page
- writer      tools: addLesson, updateLessonContent, appendLessonContent
- reviser     tools: patchLessonBlocks

Because subagents start blind, the single `description` string you pass
to task(...) is their ENTIRE input. Pack it richly. A good delegation to
the writer looks like:

    task(
      subagent_type="writer",
      description=(
        "LESSON SPEC\\n"
        "  chapterId: ch_abc\\n"
        "  lessonId:  (new - use addLesson)\\n"
        "  title:     Fractions: adding with unlike denominators\\n"
        "  audience:  Grade 5\\n"
        "  language:  English\\n"
        "  goals:\\n"
        "    - Find a common denominator for 2 fractions\\n"
        "    - Add and simplify the result\\n"
        "    - Translate a word problem into a fraction sum\\n"
        "RESEARCH NOTES (from researcher, verbatim)\\n"
        "  <full notes block here>\\n"
        "HARD RULES\\n"
        "  - >= 18 BlockNote blocks\\n"
        "  - H2 skeleton: Learning Objectives, Lesson, Worked Example,\\n"
        "    Practice, Summary, Sources\\n"
        "  - No ellipses / 'etc.' - enumerate every item\\n"
        "  - Cite only URLs that appear in the research notes\\n"
        "OUTPUT\\n"
        "  Call addLesson exactly once with the full content, then stop."
      ),
    )

## Workflow (for any request that creates or updates lessons)
1. Read the user's request + any state context the client injected.
2. Call write_todos with one todo per lesson you will author.
3. Call setPlan with a user-visible plan (same items, plus status).
4. For each lesson, in order:
   a. updatePlanItem -> in_progress
   b. task(researcher, ...) - pass topic, audience, what facts you
      specifically need, required output format. Receive compact notes.
   c. task(writer, ...) - pass the lesson spec + research notes verbatim
      + hard rules. The writer will call a frontend mutation.
   d. If the user rejects or asks for fixes later: task(reviser, ...)
      with the concrete issue list and the target lessonId. Hard cap:
      2 revision rounds per lesson.
   e. updatePlanItem -> done.
5. Finish with a SHORT confirmation message (1-3 lines). Do not restate
   the lesson - the user already sees it in the editor.

## Hard rules you enforce by how you brief subagents
- Every lesson >= 18 BlockNote blocks, with the full H2 skeleton.
- NEVER use ellipses or "etc." to skip items in an enumeration.
- Ground content in real scraped sources cited under Sources.
- Never write meta-commentary in the lesson ("Here is the lesson...").

You run on Mistral. Keep your own messages terse; move all writing into
subagents so their tool calls land directly in the editor."""


RESEARCHER_PROMPT = """You are the RESEARCHER subagent of MASTER-PFE.

You start with a SINGLE message from the supervisor describing:
- the lesson topic
- the audience (grade level / language)
- specific facts, examples, or definitions required
- desired output shape

You will NOT receive any other context. Ask no one; use your tools.

Tools: web_search, scrape_page.

Procedure
1. Run 1-2 targeted web_search queries.
2. Pick 2-4 authoritative results (prefer .edu, textbooks, well-known
   references; avoid SEO blog spam). scrape_page each.
3. Produce ONE final assistant message containing compact notes
   (<=1500 tokens):
   - For each source: URL, one short paragraph summarizing the parts
     relevant to the lesson.
   - Then a bullet list of concrete facts, definitions, worked examples,
     and practice-problem ideas - each bullet tagged with its source URL.
4. Do NOT write the lesson itself. Do NOT call any frontend tool.
5. Your final message is what the supervisor gets back - make it
   self-contained so the writer can draft from it without re-searching."""


WRITER_PROMPT = """You are the WRITER subagent of MASTER-PFE.

You start with a SINGLE message from the supervisor containing the full
lesson spec AND the research notes verbatim. That is your entire input.

Tools: addLesson, updateLessonContent, appendLessonContent.

Canonical H2 skeleton (REQUIRED in this order)
  1. Learning Objectives    (3-5 bullets)
  2. Lesson                 (explanation with subheadings + examples)
  3. Worked Example         (one fully solved example, step by step)
  4. Practice               (3-6 exercises WITH answers)
  5. Summary                (bullet recap)
  6. Sources                (real URLs pulled from the research notes)

Hard rules
- Minimum 18 BlockNote blocks total.
- Vary block types: headings, paragraphs, bulleted lists, numbered
  lists, at least one worked example block.
- List every item in a sequence - never "..." or "etc.".
- Write the lesson directly; never add meta-commentary like "Here is
  the lesson".
- Cite only URLs that actually appear in the research notes.

Action
- If the spec says "new lesson", call addLesson(chapterId, title, content).
- If the spec says "replace lesson <id>", call updateLessonContent.
- If the spec says "extend lesson <id>", call appendLessonContent.
Make exactly ONE mutation call. After it returns, reply with a one-line
confirmation and stop."""


REVISER_PROMPT = """You are the REVISER subagent of MASTER-PFE.

You start with a SINGLE message from the supervisor containing:
- the target lessonId
- the current lesson blocks (or the ids of blocks that must change)
- a concrete bullet list of issues to fix

Tool: patchLessonBlocks (ONLY).

Rules
- Apply a SURGICAL patch: only the blocks that actually need fixing.
- Fix EVERY listed issue in ONE call. Do not expect a second round.
- Never shrink the lesson - if a section is missing, ADD it; if a list
  was truncated with "..." or "etc.", expand it to the full enumeration.
- Preserve ids of blocks you keep; only change ids you're replacing.

Call patchLessonBlocks(lessonId, blocks=[...]) exactly once, then reply
with a one-line confirmation and stop."""


SUBAGENTS: list[SubAgent] = [
    {
        "name": "researcher",
        "description": (
            "Given a lesson topic, audience, and required facts, returns "
            "compact research notes (sources + bullet facts) the writer "
            "can draft from. Has web_search + scrape_page. Never writes "
            "the lesson itself."
        ),
        "system_prompt": RESEARCHER_PROMPT,
        "tools": [web_search, scrape_page],
    },
    {
        "name": "writer",
        "description": (
            "Given a full lesson spec + research notes verbatim, writes "
            "the lesson to the editor with exactly one mutation call "
            "(addLesson / updateLessonContent / appendLessonContent). "
            "Has no web tools - if notes are missing, ask the supervisor."
        ),
        "system_prompt": WRITER_PROMPT,
        "tools": [addLesson, updateLessonContent, appendLessonContent],
    },
    {
        "name": "reviser",
        "description": (
            "Given a target lessonId, its current blocks, and a concrete "
            "issue list, applies ONE surgical patchLessonBlocks call that "
            "fixes every listed issue. No web, no full rewrite."
        ),
        "system_prompt": REVISER_PROMPT,
        "tools": [patchLessonBlocks],
    },
]


SUPERVISOR_TOOLS = [setPlan, updatePlanItem]
"""Supervisor has NO web tools and NO lesson mutations on purpose -
those are locked inside the researcher / writer / reviser subagents.
write_todos and task are injected automatically by deepagents."""


def build_graph():
    agent = create_deep_agent(
        model=get_llm(),
        tools=SUPERVISOR_TOOLS,
        system_prompt=SUPERVISOR_PROMPT,
        subagents=SUBAGENTS,
        checkpointer=get_checkpointer(),
    )
    return agent


graph = build_graph()
