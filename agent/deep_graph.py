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
from agent.frontend_shells import (
    addLesson,
    appendLessonContent,
    askUser,
    patchLessonBlocks,
    updateLessonContent,
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
- askUser         - ALWAYS use this tool to collect information from the
                    user instead of asking in chat.

## Subagents (each starts BLIND - no chat history)
- researcher  tools: web_search, scrape_page
- writer      tools: addLesson, updateLessonContent, appendLessonContent
- reviser     tools: patchLessonBlocks

Pack the entire `description` string with everything the subagent needs.

## Workflow
1. Read the user's request + any state context the client injected.
2. Call write_todos with one todo per lesson; mark the first in_progress.
3. For each lesson: task(researcher) -> task(writer) -> (if needed) task(reviser).
4. Update write_todos as lessons complete.
5. Finish with a SHORT confirmation.

## Hard rules enforced via subagent briefs
- Every lesson >= 18 BlockNote blocks with full H2 skeleton.
- NEVER use ellipses or "etc." to skip items.
- Ground content in real scraped sources cited under Sources.

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

Tools: addLesson, appendLessonContent, updateLessonContent.

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
returned lessonId. After the final batch, reply with a one-line
confirmation and stop."""


REVISER_PROMPT = """You are the REVISER subagent of MASTER-PFE.

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


def build_graph():
    subagents: list[CompiledSubAgent] = [
        _build_subagent("researcher", RESEARCHER_PROMPT, [web_search, scrape_page]),
        _build_subagent("writer",     WRITER_PROMPT,     [addLesson, updateLessonContent, appendLessonContent]),
        _build_subagent("reviser",    REVISER_PROMPT,    [patchLessonBlocks]),
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
