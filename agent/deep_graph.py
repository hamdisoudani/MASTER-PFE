"""Deep-agent variant of the MASTER-PFE syllabus agent.

Railway-safe rewrite: this module previously used
``deepagents.create_deep_agent``, which force-injects ``FilesystemMiddleware``,
``SkillsMiddleware``, ``SummarizationMiddleware`` and a sandbox backend.
Those middlewares (a) mount tools (write_file / read_file / ls / execute)
that we never use, (b) try to touch a local writable root on the Railway
container's ephemeral filesystem, and (c) inflate the tool schema past
Mistral's practical tool-count sweet spot.

We now assemble the supervisor manually with:
  * ``langchain.agents.create_agent`` as the runtime
  * ``TodoListMiddleware`` for the supervisor ``write_todos`` tool
  * ``SubAgentMiddleware`` (in-memory default backend) so the
    supervisor can call ``task(...)`` to dispatch a subagent
  * One ``create_agent`` per subagent, with ONLY the tools that subagent is
    allowed to use and its own ``TodoListMiddleware`` for internal planning.

No filesystem, no skills, no summarization — nothing that depends on the
host filesystem. This works identically in local dev, Docker, and Railway.
"""
from __future__ import annotations
import logging

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware, TodoListMiddleware
from deepagents.middleware.subagents import (
    CompiledSubAgent,
    SubAgentMiddleware,
)

from agent.checkpointer import get_checkpointer
from agent.frontend_shells import askUser
from agent.llm import get_llm
from agent.tools import web_search, scrape_page, load_curriculum_tools

# (PR4) addLesson / updateLessonContent / appendLessonContent / patchLessonBlocks
# used to be frontend interrupt shells imported from agent.frontend_shells. They
# are now MCP tools served by curriculum-mcp and resolved lazily at graph build
# time via `_mcp_tools_by_name()`. See build_graph() below.
# Original import (kept for reference):
# from agent.frontend_shells import (
#     addLesson, appendLessonContent, patchLessonBlocks, updateLessonContent,
# )

logger = logging.getLogger(__name__)


SUPERVISOR_PROMPT = """You are MASTER-PFE's deep curriculum SUPERVISOR.
You are an orchestrator AND the owner of the in-memory DRAFT syllabus.
You do NOT call web tools yourself - those belong to the researcher.
You DO call draft* tools to build the syllabus skeleton and stage
lessons; persistence to Supabase is deferred to the writer/reviser
subagents only when the draft is ready to go live.

You operate BlockNote lessons for real learners (often children/students).

## Tools available to YOU (supervisor)
- write_todos                 plan the full job up front; one todo per lesson.
- task                        delegate to a subagent (researcher, writer, reviser).
- askUser                     ALWAYS use this to collect missing information
                              from the user instead of asking in chat.
- draftGetOrCreateSyllabus    bootstrap or fetch the draft for this thread.
- draftGetSyllabusOutline     inspect the current draft structure.
- draftAddChapter             add a chapter to the draft.
- draftAddLesson              stage an empty or seeded lesson in the draft.
- draftAppendLessonContent    append blocks to a draft lesson.
- draftUpdateLessonContent    overwrite a draft lesson's blocks.
- draftPatchLessonBlocks      surgical patch on a draft lesson.
- draftReadLessonBlocks       read a draft lesson before patching.
- draftSnapshot               full draft tree (use for preview / handoff).

NONE of the draft* tools touch Supabase. They mutate in-memory state
scoped to this thread_id.

## Subagents (each starts BLIND - no chat history, no draft state)
- researcher  tools: web_search, scrape_page
- writer      tools: addLesson, updateLessonContent, appendLessonContent
                     (PERSISTENT Supabase-backed - use only when a lesson
                      is ready to go live)
- reviser     tools: patchLessonBlocks
                     (PERSISTENT - surgical fixes on a published lesson)

Because subagents start blind, pack the entire `description` you pass to
`task(...)` with everything they need: the exact lesson title, the
target chapter_id, the learner level, the researcher's notes (URLs +
facts), the mandatory H2 skeleton, and - for writer/reviser - the
EXACT persistent lesson_id to write into (or instruct them to addLesson
and return the new id).

## Workflow
1. Read the user's request + any state context the host forwarded
   (thread_id, existing editor skeleton, etc.).
2. If required info is missing, call askUser ONCE with all questions batched.
3. draftGetOrCreateSyllabus(thread_id, title) to bootstrap the draft.
4. write_todos with one todo per lesson; mark the first in_progress.
5. For each lesson:
   a. task(researcher, description=<topic + level + must-cover facts>)
   b. Stage the lesson in the draft:
      draftAddChapter (if new) -> draftAddLesson -> optional
      draftAppendLessonContent / draftPatchLessonBlocks until the
      skeleton is complete and self-checks pass.
   c. When the draft lesson is ready to go live, task(writer,
      description=<final blocks + persistence instructions>) so the
      writer mirrors it into Supabase via addLesson /
      appendLessonContent. The writer returns the persistent lesson_id.
   d. If QA flags issues post-persistence, task(reviser,
      description=<persistent lesson_id + exact list of fixes>).
6. Update write_todos as lessons complete.
7. Finish with a SHORT confirmation and a draftSnapshot(thread_id) call
   so the UI can render the final preview.

## Hard rules enforced via subagent briefs
- Every lesson >= 18 BlockNote blocks with full H2 skeleton.
- NEVER use ellipses or "etc." to skip items.
- Ground content in real scraped sources cited under Sources.
- Reuse ids verbatim. Never invent ids. Do not mix draft ids with
  persistent ids when briefing the writer - give the writer the BLOCKS
  (copied from draftReadLessonBlocks) plus the target chapter_id.

You run on Mistral. Keep your own messages terse."""


RESEARCHER_PROMPT = """You are the RESEARCHER subagent of MASTER-PFE.

Tools: web_search, scrape_page.

Procedure
1. Run 1-2 targeted web_search queries.
2. scrape_page 2-4 authoritative results.
3. Produce ONE final assistant message (<=1500 tokens) with:
   - per-source: URL + short summary of relevant parts
   - bullet list of concrete facts/definitions/examples, each tagged with its source URL
4. Do NOT write the lesson. Do NOT call any frontend tool."""


WRITER_PROMPT = """You are the WRITER subagent of MASTER-PFE.

You PERSIST finalized lessons into Supabase. You do NOT touch the
draft* tools - you do not have them.

Tools (PERSISTENT, Supabase-backed):
  - addLesson(chapterId, title, blocks?) -> {lessonId}
  - appendLessonContent(lessonId, blocks)
  - updateLessonContent(lessonId, blocks)   (full overwrite - rare)

Your supervisor will hand you:
  - the target chapter_id (persistent)
  - the lesson title
  - the FULL block list already QA-ed in the draft
  - any per-batch split guidance

Canonical H2 skeleton (REQUIRED, total >= 18 blocks)
  1. Learning Objectives (3-5 bullets)
  2. Lesson
  3. Worked Example
  4. Practice (>=5 exercises WITH answers)
  5. Summary
  6. Sources (real URLs from the notes)

Write in 2-3 sequential batches against the SAME lessonId:
  Batch 1 (addLesson): H1 + hook + sections 1-2
  Batch 2 (appendLessonContent, same lessonId): sections 3-4
  Batch 3 (appendLessonContent, same lessonId): sections 5-6

Hard rules: total >= 18 blocks, vary block types, never "...", cite only
URLs from the notes, each appendLessonContent MUST reuse addLesson's
returned lessonId (NOT the draft lesson id - addLesson returns a fresh
persistent id). After the final batch, reply with the persistent
lessonId on a single line and stop."""


REVISER_PROMPT = """You are the REVISER subagent of MASTER-PFE.

You operate on PERSISTED Supabase lessons only. You do NOT have draft*
tools. Your supervisor passes you a persistent lesson_id plus the exact
list of issues (missing section, forbidden token, too few practice
items, ...).

Tool: patchLessonBlocks (ONLY).

Fix EVERY listed issue in ONE surgical patch. Never shrink the lesson.
Call patchLessonBlocks(lessonId, blocks=[...]) exactly once, then reply
with a one-line confirmation and stop."""



import os as _os


def _make_summarizer() -> SummarizationMiddleware:
    """Long-running conversation summarizer.

    Mirrors the open-swe / deepagents pattern: when the thread grows past a
    fraction of the model's context window, older messages (excluding the
    leading system prompt, which LC preserves) are replaced by an LLM-
    generated summary. This is provider-safe — LC places the summary as a
    HumanMessage/ToolMessage, never as a second SystemMessage, so Mistral /
    GPT-5 / Claude never see "System message must be at the beginning."
    """
    max_tokens = int(_os.getenv("AGENT_MAX_TOKENS_BEFORE_SUMMARY", "96000"))
    keep = int(_os.getenv("AGENT_SUMMARY_KEEP_MESSAGES", "20"))
    return SummarizationMiddleware(
        model=get_llm(),
        trigger=("tokens", max_tokens),
        keep=("messages", keep),
    )


def _build_subagent(name: str, prompt: str, tools: list) -> CompiledSubAgent:
    """Build a subagent as a CompiledSubAgent so SubAgentMiddleware doesn't
    inject its own backend/filesystem middleware stack.

    Each subagent only gets TodoListMiddleware for its own internal planning
    (lightweight, in-memory) plus exactly the tools it is allowed to use."""
    runnable = create_agent(
        model=get_llm(),
        system_prompt=prompt,
        tools=tools,
        middleware=[
            TodoListMiddleware(),
            _make_summarizer(),
        ],
        name=name,
    )
    return {
        "name": name,
        "description": f"MASTER-PFE {name} subagent.",
        "runnable": runnable,
    }


def _mcp_tools_by_name() -> dict:
    """Load curriculum-mcp tools and index them by name.

    Returns an empty dict when CURRICULUM_MCP_URL is unset or the server is
    unreachable, so the deep graph still builds for local dev / CI.
    """
    try:
        return {t.name: t for t in load_curriculum_tools()}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("deep_graph: could not load curriculum MCP tools: %s", e)
        return {}


def build_graph():
    mcp = _mcp_tools_by_name()
    # Writer + reviser (a.k.a. summarizer) keep PERSISTENT Supabase-backed tools.
    # The supervisor works against the IN-MEMORY DRAFT store so it can plan /
    # stage a syllabus without hitting the database.
    writer_tools = [mcp[n] for n in ("addLesson", "updateLessonContent", "appendLessonContent") if n in mcp]
    reviser_tools = [mcp[n] for n in ("patchLessonBlocks",) if n in mcp]
    supervisor_draft_tools = [
        mcp[n] for n in (
            "draftGetOrCreateSyllabus",
            "draftGetSyllabusOutline",
            "draftAddChapter",
            "draftAddLesson",
            "draftAppendLessonContent",
            "draftUpdateLessonContent",
            "draftPatchLessonBlocks",
            "draftReadLessonBlocks",
            "draftSnapshot",
        ) if n in mcp
    ]
    if not writer_tools:
        logger.warning("deep_graph: writer subagent has no lesson-mutation tools (curriculum-mcp unavailable)")
    if not supervisor_draft_tools:
        logger.warning("deep_graph: supervisor has no draft tools (curriculum-mcp unavailable)")

    subagents: list[CompiledSubAgent] = [
        _build_subagent("researcher", RESEARCHER_PROMPT, [web_search, scrape_page]),
        _build_subagent("writer",     WRITER_PROMPT,     writer_tools),
        _build_subagent("reviser",    REVISER_PROMPT,    reviser_tools),
    ]

    agent = create_agent(
        model=get_llm(),
        system_prompt=SUPERVISOR_PROMPT,
        tools=[askUser, *supervisor_draft_tools],
        middleware=[
            TodoListMiddleware(),
            _make_summarizer(),
            SubAgentMiddleware(
                default_model=get_llm(),
                subagents=subagents,
                general_purpose_agent=False,
            ),
        ],
        checkpointer=get_checkpointer(),
    )
    return agent


graph = build_graph()
