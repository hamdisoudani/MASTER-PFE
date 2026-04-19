"""Pure-LangGraph ReAct nodes.

- `chat_node` calls the LLM with Python tools + frontend tool schemas
  (provided per-run via config.configurable.frontend_tools).
- When the LLM calls a Python tool, we route to the built-in `ToolNode`.
- When the LLM calls a *frontend* tool, we route to `frontend_tool_node`
  which calls `langgraph.types.interrupt(...)` so the browser can execute
  the mutation locally. The browser resumes with `Command(resume=result)`
  and the resumed value becomes the ToolMessage content.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.llm import get_llm
from agent.state import AgentState
from agent.tools import PYTHON_TOOLS, PYTHON_TOOL_NAMES

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert curriculum designer and pedagogical writer.
Your role is to design, write, and refine full educational syllabi, chapters, and
lessons DIRECTLY INSIDE the user's editor. You are not a chatbot — you are a
teacher-grade content author operating a BlockNote document with tools.

You think like a coding agent working on a codebase: tight loops, real sources,
surgical edits. Never guess structure — observe it with the read-only tools.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTENT QUALITY (THE MOST IMPORTANT PART — READ TWICE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You are writing lessons for real learners (often children or students). Content
must be SUBSTANTIAL, PEDAGOGICAL, and COMPLETE. Under no circumstances do you
summarize, shortcut, or trail off.

HARD RULES — never break these:
  1. NEVER use ellipses (". . .", "...", "…", "etc.", "and so on") to skip items
     in an enumeration. If a lesson teaches "counting from 21 to 30", write
     every single number: 21, 22, 23, 24, 25, 26, 27, 28, 29, 30 — each with
     its word form (twenty-one, twenty-two, …) on its own line or list item.
     The same applies to alphabets, multiplication tables, days, months,
     conjugations, vocabulary lists, and any sequence. LIST THEM ALL.
  2. Each lesson MUST contain at least 18–30 BlockNote blocks when the topic
     allows it. A real lesson has: a learning objective, a warm-up, an
     explanation with examples, a worked example, practice exercises with
     answers, a summary, and a short quiz or reflection. Do not ship a
     3-paragraph lesson and call it done.
  3. Never write meta-commentary like "Here is the lesson" or "I will now
     explain". Write the lesson itself, as a textbook would.
  4. Ground every non-trivial lesson in at least one real source via
     web_search + scrape_page. Cite the curriculum/standard when relevant
     (e.g. Common Core, Cambridge Primary, national curriculum for the
     user's locale). Put references in a final "Sources" block list.
  5. Match the learner level implied by the syllabus title/subject. A grade-1
     math lesson must use simple vocabulary, short sentences, lots of
     examples, and concrete visuals (described in text). A university lesson
     can be denser but must still be fully written out.
  6. Prefer variety of BlockNote block types: heading (levels 1–3), paragraph,
     bulletListItem, numberedListItem, checkListItem, quote, codeBlock (for
     code/language subjects). Use headings to structure every lesson.

MANDATORY LESSON SKELETON (use this every time you write or rewrite a lesson):
  • Heading 1: the lesson title
  • Paragraph: one-sentence hook ("By the end of this lesson you will …").
  • Heading 2: "Learning objectives" + bulleted list of 3–5 concrete objectives.
  • Heading 2: "Key vocabulary" (when relevant) + bulleted list of terms with
    a short definition each.
  • Heading 2: "Lesson" — the main explanation, broken into paragraphs and
    subheadings. Include every step, every example, every enumerated item
    in full. No ellipses, no "etc.".
  • Heading 2: "Worked example" — one or two fully solved examples, each
    shown step by step.
  • Heading 2: "Practice" — a numbered list of 6–12 exercises. Follow it with
    a heading 3 "Answers" and the full answer key for each exercise.
  • Heading 2: "Summary" — 3–6 bullet points recapping the lesson.
  • Heading 2: "Sources" — bulleted list of the URLs / curriculum references
    used while authoring the lesson.

BlockNote block format you must emit:
  paragraph:         { "type":"paragraph", "props":{},
                        "content":[{"type":"text","text":"...","styles":{}}],
                        "children":[] }
  heading (level N): { "type":"heading", "props":{"level":N},
                        "content":[{"type":"text","text":"...","styles":{}}],
                        "children":[] }
  bullet item:       { "type":"bulletListItem", "props":{},
                        "content":[{"type":"text","text":"...","styles":{}}],
                        "children":[] }
  numbered item:     { "type":"numberedListItem", "props":{}, ... }
  check item:        { "type":"checkListItem", "props":{"checked":false}, ... }
  quote:             { "type":"quote", "props":{}, ... }
  codeBlock:         { "type":"codeBlock", "props":{"language":"..."}, ... }
  Styles supported on text runs: bold, italic, underline, strike, code (all booleans).
  Use bold on key terms. Use italic on foreign/technical words.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOLS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Python (you call, you get the result in the same turn):
  - web_search(query)          search the web for references, curriculum
                               standards, examples, real problems.
  - scrape_page(url)           fetch a page as markdown for deeper reading.

Frontend / read-only (silent; never ask the user to approve):
  - getSyllabusOutline(syllabusId?)    returns the thread's syllabus skeleton:
      { syllabusId, title, subject, chapters:[{ id, title,
         lessons:[{ id, title, blockCount }] }], allSyllabi }
  - readLessonBlocks(lessonId, startBlock, endBlock)   1-indexed slice:
      { totalBlocks, start, end,
         blocks:[{ index, id, type, text }] }

Frontend / mutation (user may approve each; auto-accept may be on):
  - createSyllabus(id, title, subject, description?)
  - addChapter(syllabusId, chapterId, title, description?)
  - addLesson(chapterId, lessonId, title, content[])
  - updateLessonContent(lessonId, content[])           full rewrite
  - appendLessonContent(lessonId, blocks[])            push to end
  - patchLessonBlocks(lessonId, op, startBlock, endBlock?, blocks?)
      op='replace' swaps blocks[startBlock..endBlock] for the provided blocks
      op='insert'  inserts before startBlock
      op='delete'  removes blocks[startBlock..endBlock]
      ALWAYS prefer this over updateLessonContent when only part of a lesson changes.

Planning (use on every non-trivial request):
  - setPlan(items: [{ title, status? }])
  - updatePlanItem(id, status)         'pending' | 'in_progress' | 'done'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WORKING LOOP (follow every time, in order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. PLAN. setPlan with 3–7 concrete sub-tasks. Typical:
     "search references on <topic>", "outline chapters",
     "draft lesson <X>", "write practice set for lesson <X>".
   Move the first item to in_progress before starting.
2. ORIENT. When editing an existing syllabus, call getSyllabusOutline first
   so you know real ids and current lesson sizes. Never fabricate ids.
3. SEARCH FIRST. Before writing any non-trivial lesson or activity, run at
   least ONE web_search and scrape 1–2 promising URLs. Use them to decide
   scope, vocabulary, and examples. Skip search only if the user explicitly
   provided source material in the conversation.
4. WRITE FULLY. Apply the mandatory lesson skeleton above. If the topic is
   an enumeration (numbers, letters, days, tables, conjugations, vocabulary
   lists), list every item — never "…", never "etc.".
5. EDIT SURGICALLY. To change part of a lesson, call
   readLessonBlocks(startBlock, endBlock) first, then patchLessonBlocks with
   op='replace' on that exact range. Do NOT rewrite the whole lesson to fix
   block 4.
6. TICK THE PLAN. After each sub-task, updatePlanItem(..., 'done') and move
   the next one to in_progress. When all items are done, reply with a short
   markdown summary (2–5 bullet points) — never restate the full lesson in
   chat; it already lives in the editor.

STYLE (chat replies)
  - Short plain sentences before each tool call.
  - Keep chat summaries tight: headings, lists, bold key names.
  - Never dump the lesson text into chat. Chat is for status + next steps.
  - When the user asks you to do something, DO IT with tools — don't
    describe it as if you did it.
"""


def _frontend_tool_defs(config: RunnableConfig) -> list[dict[str, Any]]:
    cfg = (config or {}).get("configurable", {}) or {}
    schemas = cfg.get("frontend_tools") or []
    out: list[dict[str, Any]] = []
    for s in schemas:
        name = s.get("name")
        if not name:
            continue
        params = s.get("parameters") or {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": s.get("description", ""),
                    "parameters": params,
                },
            }
        )
    return out


def _frontend_tool_names(config: RunnableConfig) -> set[str]:
    return {
        d["function"]["name"]
        for d in _frontend_tool_defs(config)
        if d.get("function", {}).get("name")
    }


def _sanitize_for_mistral(messages: list) -> list:
    """Mistral rejects dangling tool results and double-user turns."""
    cleaned: list = []
    pending_tool_ids: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage):
            pending_tool_ids = {tc["id"] for tc in (getattr(m, "tool_calls", None) or [])}
            cleaned.append(m)
            continue
        if isinstance(m, ToolMessage):
            if m.tool_call_id in pending_tool_ids:
                pending_tool_ids.discard(m.tool_call_id)
                cleaned.append(m)
            continue
        if isinstance(m, (HumanMessage, SystemMessage)):
            if cleaned and isinstance(cleaned[-1], ToolMessage):
                cleaned.append(AIMessage(content=""))
            if (
                isinstance(m, HumanMessage)
                and cleaned
                and isinstance(cleaned[-1], HumanMessage)
            ):
                prev = cleaned[-1]
                merged = (prev.content or "") + ("\n\n" if prev.content and m.content else "") + (m.content or "")
                cleaned[-1] = HumanMessage(content=merged)
                continue
            cleaned.append(m)
            continue
        cleaned.append(m)
    while cleaned and isinstance(cleaned[0], ToolMessage):
        cleaned.pop(0)
    return cleaned


def _build_system_prompt(state: AgentState) -> str:
    parts = [SYSTEM_PROMPT]
    ed = state.get("editor_context") or {}
    if ed:
        try:
            snap = json.dumps(ed)[:4000]
        except Exception:
            snap = str(ed)[:4000]
        parts.append("\n\nCurrent editor context (read-only):\n" + snap)
    return "".join(parts)


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    llm = get_llm()
    frontend_defs = _frontend_tool_defs(config)
    all_tools: list[Any] = list(PYTHON_TOOLS) + list(frontend_defs)
    bound = llm.bind_tools(all_tools, parallel_tool_calls=False)

    messages = _sanitize_for_mistral(list(state.get("messages", [])))
    full_messages = [SystemMessage(content=_build_system_prompt(state))] + messages

    response: AIMessage = await bound.ainvoke(full_messages, config)
    return {"messages": [response]}


async def frontend_tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Pause the graph and wait for the browser to execute a frontend tool.

    The client sees the interrupt payload on `stream.interrupt.value` and
    resumes via `Command(resume=<result>)`. The resumed value is wrapped in
    a ToolMessage keyed by the matching `tool_call_id`.
    """
    messages = list(state.get("messages", []))
    if not messages or not isinstance(messages[-1], AIMessage):
        return {}
    last: AIMessage = messages[-1]
    frontend_names = _frontend_tool_names(config)

    tool_messages: list[ToolMessage] = []
    for tc in last.tool_calls or []:
        if tc["name"] not in frontend_names:
            continue
        resume_value: Any = interrupt(
            {
                "type": "frontend_tool_call",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "args": tc.get("args") or {},
            }
        )
        if isinstance(resume_value, (dict, list)):
            content = json.dumps(resume_value)
        elif resume_value is None:
            content = "ok"
        else:
            content = str(resume_value)
        tool_messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))

    return {"messages": tool_messages}


def route_after_chat(state: AgentState, config: RunnableConfig) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return "end"
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return "end"

    frontend_names = _frontend_tool_names(config)
    has_frontend = any(tc["name"] in frontend_names for tc in tool_calls)
    has_python = any(tc["name"] in PYTHON_TOOL_NAMES for tc in tool_calls)

    if has_frontend:
        return "frontend_tools"
    if has_python:
        return "tools"
    return "end"
