"""
chat_node  -- main LLM node.
  - Binds Python tools + CopilotKit frontend tools to the LLM.
  - AG-UI handles frontend tool execution automatically (execute hooks on the
    frontend side); the agent does NOT need to intercept, stash, or inject
    synthetic ToolMessages for frontend calls.
  - Summarization middleware compresses old messages when history > MAX_MESSAGES.
  - Extracts ToolMessage results and persists them into named state fields
    so the frontend can render plan / search / scrape live.

tools_node -- ToolNode that executes Python-side tools only.
"""
import json
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .llm import get_llm
from .tools import PYTHON_TOOLS

tools_node = ToolNode(PYTHON_TOOLS)
PYTHON_TOOL_NAMES = {t.name for t in PYTHON_TOOLS}


def _get_frontend_tool_names(state: AgentState) -> set:
    ck = state.get("copilotkit") or {}
    actions = (
        ck.get("actions") or []
        if isinstance(ck, dict)
        else getattr(ck, "actions", None) or []
    )
    names: set = set()
    for a in actions:
        if isinstance(a, dict):
            name = (
                (a.get("function") or {}).get("name")
                or a.get("name")
            )
            if name:
                names.add(name)
    return names


MAX_MESSAGES = 30
KEEP_RECENT  = 14


async def _maybe_summarize(messages: list, llm) -> list:
    if len(messages) <= MAX_MESSAGES:
        return messages

    to_compress = messages[:-KEEP_RECENT]
    recent      = messages[-KEEP_RECENT:]

    lines = []
    for m in to_compress:
        role = getattr(m, "type", "msg")
        raw  = m.content if isinstance(m.content, str) else json.dumps(m.content)[:300]
        lines.append(f"[{role}] {raw[:250]}")

    summary_req = HumanMessage(
        content=(
            "Summarize this conversation for an AI course-builder assistant.\n"
            "Focus on: which syllabus was created, which chapters and lessons were added, "
            "what research was done, and what still needs to be done.\n"
            "Be concise -- max 200 words.\n\nCONVERSATION:\n"
            + "\n".join(lines)
        )
    )

    try:
        resp    = await llm.ainvoke([summary_req])
        summary = resp.content
    except Exception:
        summary = "[Summary unavailable -- context compressed.]"

    compressed = SystemMessage(content=f"[Prior conversation -- compressed]\n{summary}")
    return [compressed] + list(recent)


SYSTEM_PROMPT = """You are Syllabus AI -- an expert course-creation assistant for educators.

You have two categories of tools:
  * RESEARCH tools  (Python, server-side): plan_tasks, update_plan_task, search_web, scrape_website
  * COURSE-BUILDING tools (frontend, browser-side): create_syllabus, add_chapter, add_lesson,
    update_lesson_content, remove_chapter, remove_lesson

Both sets are REAL callable tools. Call them as tool/function calls -- never describe their output in plain text.

CRITICAL RULES
==============

RULE 1 -- ALWAYS USE TOOL CALLS, NEVER PLAIN TEXT
  Do NOT write syllabus / chapter / lesson content in your response text.
  ALWAYS call the tool: create_syllabus(), add_chapter(), add_lesson().
  After research -> call add_lesson() immediately. Do not describe the content.

RULE 2 -- ONE COURSE-BUILDING TOOL CALL PER RESPONSE
  Call exactly one frontend tool per response (add_chapter OR add_lesson, not both).
  You can combine one backend tool (update_plan_task) with one frontend tool if needed.

RULE 3 -- COMPLETE ALL PLANNED STEPS
  Execute every step you planned. Never pause mid-plan to ask for permission.
  After every step call update_plan_task(id, "done") then move to the next step.

WORKFLOW
========

1. PLAN
   plan_tasks(tasks: list[str]) -> List every step before starting. Call this once.
   update_plan_task(task_id: int, status: "pending"|"in_progress"|"done")
     -> Before each step: in_progress. After each step: done.

2. RESEARCH (one search per lesson topic is enough)
   search_web(query, country="us", num_results=6)
   scrape_website(url: str)

3. BUILD (frontend tools -- executed by the browser via AG-UI execute hooks)
   create_syllabus(id, title, subject, description?)   -> id = url slug, call once
   add_chapter(syllabusId, chapterId, title, description?)
   add_lesson(chapterId, lessonId, title, content)     -> content = BlockNote JSON array
   update_lesson_content(lessonId, content)
   remove_chapter(chapterId) / remove_lesson(lessonId)

BLOCKNOTE JSON -- content format for add_lesson (minimum 6 blocks)
==================================================================

[
  { "id": "<lessonId>-h1", "type": "heading",
    "props": { "textColor": "default", "backgroundColor": "default", "textAlignment": "left", "level": 1 },
    "content": [{ "type": "text", "text": "Lesson Title", "styles": {} }], "children": [] },
  { "id": "<lessonId>-p1", "type": "paragraph",
    "props": { "textColor": "default", "backgroundColor": "default", "textAlignment": "left" },
    "content": [{ "type": "text", "text": "Engaging intro.", "styles": {} }], "children": [] },
  { "id": "<lessonId>-h2", "type": "heading",
    "props": { "textColor": "default", "backgroundColor": "default", "textAlignment": "left", "level": 2 },
    "content": [{ "type": "text", "text": "Section Title", "styles": {} }], "children": [] },
  { "id": "<lessonId>-b1", "type": "bulletListItem",
    "props": { "textColor": "default", "backgroundColor": "default", "textAlignment": "left" },
    "content": [{ "type": "text", "text": "Key point.", "styles": {} }], "children": [] },
  { "id": "<lessonId>-b2", "type": "bulletListItem",
    "props": { "textColor": "default", "backgroundColor": "default", "textAlignment": "left" },
    "content": [{ "type": "text", "text": "Another point.", "styles": {} }], "children": [] },
  { "id": "<lessonId>-p2", "type": "paragraph",
    "props": { "textColor": "default", "backgroundColor": "default", "textAlignment": "left" },
    "content": [{ "type": "text", "text": "Summary / bridge to next lesson.", "styles": {} }], "children": [] }
]

STRICT: content is always an array, children is always [], ids are unique and prefixed with lessonId,
heading needs level in props, codeBlock needs language in props.

EXAMPLE
=======

User: "build a Python basics course"
Turn 1:  plan_tasks(["Research","create_syllabus","add_chapter ch1","add_lesson l1-1","add_lesson l1-2"])
Turn 2:  update_plan_task(0,"in_progress") + search_web("Python basics variables")
Turn 3:  update_plan_task(0,"done") + update_plan_task(1,"in_progress") + create_syllabus("python-basics","Python Basics","Programming")
Turn 4:  update_plan_task(1,"done") + update_plan_task(2,"in_progress") + add_chapter("python-basics","ch1","Getting Started")
Turn 5:  update_plan_task(2,"done") + update_plan_task(3,"in_progress") + add_lesson("ch1","l1-1","Variables",[<BlockNote JSON>])
Turn 6:  update_plan_task(3,"done") + update_plan_task(4,"in_progress") + add_lesson("ch1","l1-2","Loops",[<BlockNote JSON>])
Turn 7:  update_plan_task(4,"done") -- "Course complete!"
"""


async def chat_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Main LLM node. Binds all tools (Python + frontend) to the LLM and invokes it.
    AG-UI handles frontend tool execution via execute hooks -- no manual interception needed.
    """
    ck = state.get("copilotkit") or {}
    ck_dict = ck if isinstance(ck, dict) else {}

    raw_messages     = list(state["messages"])
    frontend_actions = ck_dict.get("actions") or []

    llm            = get_llm()
    all_tools      = list(PYTHON_TOOLS) + list(frontend_actions)
    llm_with_tools = llm.bind_tools(all_tools) if all_tools else llm

    summarized = await _maybe_summarize(raw_messages, llm)
    messages   = [SystemMessage(content=SYSTEM_PROMPT)] + summarized

    response = await llm_with_tools.ainvoke(messages, config=config)

    state_updates: dict = {"messages": [response]}

    current_plan: list = list(state.get("plan") or [])

    for msg in raw_messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
        except Exception:
            continue

        tool_name = getattr(msg, "name", None)

        if tool_name == "plan_tasks" and isinstance(data, dict):
            tasks = data.get("tasks") or []
            current_plan = [
                {"id": i, "task": t, "status": "pending"}
                for i, t in enumerate(tasks)
            ]
            state_updates["plan"] = current_plan

        elif tool_name == "update_plan_task" and isinstance(data, dict):
            task_id = data.get("task_id")
            status  = data.get("status")
            if task_id is not None and status:
                current_plan = [
                    {**t, "status": status} if t["id"] == task_id else t
                    for t in current_plan
                ]
                state_updates["plan"] = current_plan

        elif tool_name == "search_web":
            results = data.get("results") or (data if isinstance(data, list) else [])
            state_updates["search_results"] = results

        elif tool_name == "scrape_website":
            state_updates["scraped_content"] = (
                data.get("content") or data.get("markdown") or str(data)[:4000]
            )

    return state_updates
