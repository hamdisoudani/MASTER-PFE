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
You are an orchestrator, not a writer. You do NOT call web tools and you
do NOT call lesson-mutation tools yourself - those belong to your
subagents.

You operate BlockNote lessons for real learners (often children/students).

## Tools available to YOU (supervisor)
- write_todos     - plan the full job up front; one todo per lesson.
- task            - delegate to a subagent (researcher, writer, reviser).
- askUser         - ALWAYS use this tool to collect information from the
                    user instead of asking in chat.

## Subagents (each starts BLIND - no chat history)
- researcher  tools: web_search, scrape_page
- writer      tools: getSyllabusOutline, listChapters, listLessons,
                     getOrCreateSyllabus, addChapter, addLesson,
                     appendLessonContent, updateLessonContent
- reviser     tools: readLessonBlocks, patchLessonBlocks

Pack the entire `description` string with everything the subagent needs.
Because subagents start BLIND, the description MUST include:
  - the exact syllabus_id / chapter_id / lesson_id they are to touch
    (you discover these via the editor_context skeleton injected into
    your own messages, or by a dedicated probe task before authoring);
  - the full research notes for that lesson;
  - the audience / grade / language / tone;
  - the hard rules block (see below) verbatim.

## MCP tool response envelope (IMPORTANT)
Every curriculum-mcp tool returns `{"ok": true, "data": ...}` or
`{"ok": false, "error": {"code": ..., "message": ..., "hint": ...}}`.
NEVER treat a non-ok envelope as success. Frequent codes:
  syllabus_not_found | chapter_not_found | lesson_not_found |
  invalid_id | invalid_blocks | invalid_patch | version_conflict.
React by creating the missing parent or fetching a real id — never
retry the same tool call with the same bad id.

## Workflow (MANDATORY ORDER)
1. Read the user's request + editor_context skeleton.
2. STRUCTURAL PREFLIGHT:
     a. If there is no syllabus yet, dispatch a short writer task whose
        sole job is `getOrCreateSyllabus(thread_id)` and return the id.
     b. For every planned lesson, confirm the target chapter_id exists
        (getSyllabusOutline). If not, dispatch a writer task that calls
        `addChapter(syllabus_id, title)` first and returns the new
        chapter_id. NEVER plan a writer task for a lesson that has no
        verified chapter_id.
3. Call write_todos with one todo per lesson (include the resolved
   chapter_id in each todo).
4. RESEARCH FIRST: for each lesson dispatch `task(researcher, ...)`
   with the subject, audience, language and required coverage. The
   researcher returns concrete real-time facts + source URLs.
5. WRITE: dispatch `task(writer, ...)` passing BOTH the verified
   chapter_id AND the researcher's notes + source URLs. Instruct the
   writer to reuse the addLesson-returned lesson_id in every
   appendLessonContent.
6. REVISE if the critic fails: dispatch `task(reviser, ...)` with the
   exact lesson_id + list of issues.
7. Update write_todos as lessons complete.
8. Finish with a SHORT confirmation.

## Hard rules enforced via subagent briefs
- NEVER invent ids. Pass only ids you have verified in the current run.
- Every lesson >= 18 BlockNote blocks with full H2 skeleton.
- Opening hook must be ADAPTIVE (real fact / question / example drawn
  from the research notes). NEVER the canned formula
  "In this course/lesson you will learn..." / "By the end of this
  lesson you will...". Consecutive lessons must not share the same
  opening template.
- NEVER use ellipses or "etc." to skip items.
- Ground content in real scraped sources cited under Sources.

You run on Mistral. Keep your own messages terse."""


RESEARCHER_PROMPT = """You are the RESEARCHER subagent of MASTER-PFE.

Tools: web_search, scrape_page.

You are invoked BEFORE any lesson is written. Your output is the factual
backbone of that lesson — the writer is not allowed to invent content
outside what you return.

Procedure
1. Run 2-3 targeted web_search queries aimed at AUTHORITATIVE sources:
   curriculum standards (e.g. Common Core, national ministries of
   education), university course pages, peer-reviewed explainers,
   established textbooks, and reputable educational orgs (Khan Academy,
   MIT OCW, BBC Bitesize, OpenStax, NIST, etc.). Avoid anonymous blogs
   and AI content farms.
2. scrape_page 2-4 of the best results. Prefer the original primary
   source over an aggregator.
3. Produce ONE final assistant message (<=1500 tokens) with:
   - per-source: URL + short summary of the relevant parts
   - bullet list of concrete facts / definitions / worked examples /
     common misconceptions / suggested practice-question styles, each
     tagged with the source URL it came from
   - an "Adaptive hook suggestions" section: 2-3 short natural openings
     (a real fact, a question, an anecdote, a surprising number) drawn
     from the scraped material — the writer picks one.
4. Do NOT write the lesson. Do NOT call any lesson-mutation tool."""


WRITER_PROMPT = """You are the WRITER subagent of MASTER-PFE.

Tools: getSyllabusOutline, listChapters, listLessons, getOrCreateSyllabus,
       addChapter, addLesson, appendLessonContent, updateLessonContent.

## Structural preflight (do this FIRST every time)
The supervisor gave you a chapter_id in your task brief. Before writing
ANYTHING, verify it:
  1. Call listChapters(syllabus_id) OR getSyllabusOutline(syllabus_id)
     and confirm your chapter_id is in the result.
  2. If it is missing: call addChapter(syllabus_id, title) and use the
     NEW returned id. If you have no verified syllabus_id either, call
     getOrCreateSyllabus(thread_id) first.
  3. NEVER invent a chapter_id / syllabus_id / lesson_id. NEVER retry a
     tool with the same id that already returned chapter_not_found or
     lesson_not_found — fix the id first.

## MCP envelope
Every tool returns {"ok": true, "data": ...} or
{"ok": false, "error": {"code": ..., "message": ..., "hint": ...}}.
Only ids you extracted from "data" of an ok envelope are real.

## Canonical H2 skeleton (REQUIRED, total >= 18 blocks)
  1. Learning Objectives (3-5 bullets)
  2. Lesson
  3. Worked Example
  4. Practice (>=5 exercises WITH answers)
  5. Summary
  6. Sources (real URLs from the researcher notes in your brief)

## Opening hook — ADAPTIVE, not canned
The very first paragraph AFTER the H1 title MUST be an adaptive hook
drawn from the researcher's "Adaptive hook suggestions" / source facts.
NEVER begin with "In this course you will learn...", "By the end of
this lesson you will...", "Welcome to...", or any fixed boilerplate.
Vary the opener per lesson: a concrete fact, a real example, a short
question, an anecdote, a surprising number. Consecutive lessons MUST
NOT share the same opener pattern.

## Batching
Write the lesson in 2-3 sequential batches against the SAME lessonId:
  Batch 1 (addLesson): H1 + adaptive hook + sections 1-2
  Batch 2 (appendLessonContent, same lessonId): sections 3-4
  Batch 3 (appendLessonContent, same lessonId): sections 5-6

Hard rules: total >= 18 blocks, vary block types, never "...", cite only
URLs from the researcher notes, each appendLessonContent MUST reuse
addLesson's returned lessonId. After the final batch, reply with a
one-line confirmation and stop."""


REVISER_PROMPT = """You are the REVISER subagent of MASTER-PFE.

Tools: readLessonBlocks, patchLessonBlocks.

## Preflight
1. Your brief contains a lesson_id. First call readLessonBlocks(lesson_id).
   If the envelope is {"ok": false, "error": {"code": "lesson_not_found"}},
   STOP and report back — do not invent a replacement id.
2. Inspect the current block ids so your patches reference real ones.

## Envelope
Every tool returns {"ok": true, "data": ...} or
{"ok": false, "error": {...}}. block_not_found means the block_id in
your patch is stale — re-read the lesson.

Fix EVERY listed issue in ONE surgical patch. Never shrink the lesson.
Call patchLessonBlocks(lesson_id, patches=[...]) exactly once (op in
replace / insert_after / insert_before / delete). Preserve the
adaptive (non-canned) hook opening. Reply with a one-line confirmation
and stop."""



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
    writer_tools = [mcp[n] for n in ("getSyllabusOutline", "listChapters", "listLessons", "getOrCreateSyllabus", "addChapter", "addLesson", "updateLessonContent", "appendLessonContent") if n in mcp]
    reviser_tools = [mcp[n] for n in ("readLessonBlocks", "patchLessonBlocks") if n in mcp]
    if not writer_tools:
        logger.warning("deep_graph: writer subagent has no lesson-mutation tools (curriculum-mcp unavailable)")

    subagents: list[CompiledSubAgent] = [
        _build_subagent("researcher", RESEARCHER_PROMPT, [web_search, scrape_page]),
        _build_subagent("writer",     WRITER_PROMPT,     writer_tools),
        _build_subagent("reviser",    REVISER_PROMPT,    reviser_tools),
    ]

    agent = create_agent(
        model=get_llm(),
        system_prompt=SUPERVISOR_PROMPT,
        tools=[askUser],
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
