"""
chat_node  — main LLM node with:
  - Summarization middleware: compresses old messages when history > MAX_MESSAGES
  - Binds Python tools + CopilotKit frontend tools to the LLM
  - Extracts ToolMessage results and persists them into named state fields
    so the frontend can render plan/search/scrape live

tools_node — ToolNode that executes the Python-side tools
"""
import json
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .llm import get_llm
from .tools import PYTHON_TOOLS

# ---- tool executor node (used by graph.py) -----------------------------------
tools_node = ToolNode(PYTHON_TOOLS)
# ------------------------------------------------------------------------------

PYTHON_TOOL_NAMES = {"plan_tasks", "update_plan_task", "search_web", "scrape_website"}

# ------------------------------------------------------------------------------
# Summarization middleware
# ------------------------------------------------------------------------------

MAX_MESSAGES = 20     # compress when history exceeds this count
KEEP_RECENT = 8       # always keep the last N messages verbatim

async def _maybe_summarize(messages: list, llm) -> list:
    """
    When the message list is too long, compress the oldest messages into a
    single SystemMessage summary so we never blow the context window.
    The most recent KEEP_RECENT messages are always kept verbatim.
    """
    if len(messages) <= MAX_MESSAGES:
        return messages

    to_compress = messages[:-KEEP_RECENT]
    recent = messages[-KEEP_RECENT:]

    lines = []
    for m in to_compress:
        role = getattr(m, "type", "msg")
        raw = m.content if isinstance(m.content, str) else json.dumps(m.content)[:300]
        lines.append(f"[{role}] {raw[:250]}")

    summary_request = HumanMessage(
        content=(
            "Summarize this conversation for an AI course-builder assistant. "
            "Focus on: which syllabus was created, which chapters and lessons were added, "
            "what research was done (key search queries and findings), and what still needs to be done. "
            "Be concise — max 200 words.\n\nCONVERSATION:\n"
            + "\n".join(lines)
        )
    )

    try:
        resp = await llm.ainvoke([summary_request])
        summary_content = resp.content
    except Exception:
        summary_content = "[Summary unavailable — context compressed.]"

    compressed = SystemMessage(
        content=f"[Prior conversation — compressed]\n{summary_content}"
    )
    return [compressed] + list(recent)

# ------------------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are Syllabus AI — an expert course-creation assistant for educators.

Your job: build complete, beautifully structured course syllabi with rich, accurate lesson content.
You have both RESEARCH tools (Python-side) and COURSE-BUILDING tools (frontend-side).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — PLAN FIRST, THEN EXECUTE WITH LIVE UPDATES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

plan_tasks(tasks: list[str])
  → Call this FIRST for any request with 2+ steps.
  → After plan_tasks, immediately start executing — call update_plan_task for each step.

update_plan_task(task_id: int, status: 'pending'|'in_progress'|'done')
  → Call BEFORE starting each step:   update_plan_task(task_id=N, status='in_progress')
  → Call AFTER completing each step:  update_plan_task(task_id=N, status='done')
  → This powers the live progress checklist shown to the user. Always do this.

Example workflow:
  plan_tasks(["Search terminology", "create_syllabus", "add_chapter ch1", "add_lesson l1-1"])
  update_plan_task(0, 'in_progress') → search_web(...) → update_plan_task(0, 'done')
  update_plan_task(1, 'in_progress') → create_syllabus(...) → update_plan_task(1, 'done')
  update_plan_task(2, 'in_progress') → add_chapter(...) → update_plan_task(2, 'done')
  update_plan_task(3, 'in_progress') → add_lesson(...) → update_plan_task(3, 'done')

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — RESEARCH (before writing any lesson)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

search_web(query, country="us", time_period="", num_results=6)
  → Search for: correct vocabulary, standard curriculum, definitions, examples.
  → country: us, fr, gb, de, jp, ma, dz, tn...
  → time_period: '' (any), 'd' (day), 'w' (week), 'm' (month), 'y' (year)

scrape_website(url: str)
  → Get full markdown from a promising search result (Wikipedia, Khan Academy, etc.)
  → Use this content to write accurate, specific lesson blocks — not generic filler.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — BUILD THE COURSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

create_syllabus(id, title, subject, description?)
  → Call ONCE. id = url-friendly slug e.g. "python-beginners".

add_chapter(syllabusId, chapterId, title, description?)
  → Add all chapters before adding lessons.

add_lesson(chapterId, lessonId, title, content)
  → content = BlockNote JSON array (minimum 8 blocks — see format below).
  → Use research from search_web / scrape_website to write real content.

update_lesson_content(lessonId, content)
  → Fix render errors or improve an existing lesson.

remove_chapter(chapterId) / remove_lesson(lessonId)
  → Remove items if needed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LESSON QUALITY — MINIMUM STANDARDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Each lesson MUST contain AT LEAST 8 blocks:
  ✓ 1× heading level 1  — lesson title
  ✓ 1× paragraph        — engaging intro (3-5 sentences, mention real-world relevance)
  ✓ 1-2× heading level 2 — section titles
  ✓ 3-5× paragraphs or bulletListItems — core content with specifics from research
  ✓ 1× numbered or bullet list — key takeaways, steps, or examples
  ✓ 1× paragraph — summary / bridge to next lesson

NO FILLER. Every sentence must teach something specific.
If you searched/scraped, USE that data in your lesson content.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLOCKNOTE JSON FORMAT — follow exactly
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "id": "<lessonId>-<unique-suffix>",
  "type": "heading|paragraph|bulletListItem|numberedListItem|codeBlock|quote",
  "props": {
    "textColor": "default",
    "backgroundColor": "default",
    "textAlignment": "left",
    "level": 1,           // heading ONLY
    "language": "python"  // codeBlock ONLY
  },
  "content": [{ "type": "text", "text": "...", "styles": {} }],
  "children": []
}

STRICT RULES:
  1. Every id globally unique, prefixed with lessonId (e.g. "l1-1-h1", "l1-1-p2")
  2. "content" is ALWAYS an array — never null, never a plain string
  3. "children" is ALWAYS [] (empty array)
  4. heading MUST have "level": 1|2|3 in props
  5. codeBlock MUST have "language": "python"|"js"|"bash"|"sql"|... in props
  6. No extra keys beyond id, type, props, content, children

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ERROR HANDLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If renderErrors is non-empty → call update_lesson_content immediately.
After all tool calls → confirm in natural language what was built.
"""

# ------------------------------------------------------------------------------
# Main chat node
# ------------------------------------------------------------------------------

async def chat_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Main agent node:
    1. Compress message history if it's too long (summarization middleware)
    2. Bind all tools (Python + CopilotKit frontend) to the LLM
    3. Invoke the LLM
    4. Extract ToolMessage results → update plan/search/scrape state fields
    """
    ck = state.get("copilotkit") or {}
    frontend_actions = (
        ck.get("actions") or [] if isinstance(ck, dict)
        else getattr(ck, "actions", None) or []
    )

    llm = get_llm()
    all_tools = list(PYTHON_TOOLS) + list(frontend_actions)
    llm_with_tools = llm.bind_tools(all_tools) if all_tools else llm

    raw_messages = list(state["messages"])
    summarized_messages = await _maybe_summarize(raw_messages, llm)

    messages = [SystemMessage(content=SYSTEM_PROMPT)] + summarized_messages
    response = await llm_with_tools.ainvoke(messages, config=config)

    state_updates: dict = {"messages": [response]}

    # Carry forward the current plan so update_plan_task can mutate it
    current_plan: list = list(state.get("plan") or [])

    for msg in raw_messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
        except Exception:
            continue

        tool_name = getattr(msg, "name", None)

        if tool_name == "plan_tasks" and isinstance(data, list):
            current_plan = data
            state_updates["plan"] = current_plan
            state_updates["current_activity"] = f"Planning {len(data)} steps"

        elif tool_name == "update_plan_task" and isinstance(data, dict) and data.get("ok"):
            task_id = data.get("task_id")
            new_status = data.get("status")
            current_plan = [
                {**t, "status": new_status} if t["id"] == task_id else t
                for t in current_plan
            ]
            state_updates["plan"] = current_plan
            task_label = next(
                (t["task"] for t in current_plan if t["id"] == task_id), ""
            )
            if new_status == "in_progress":
                state_updates["current_activity"] = f"Working on: {task_label}"
            elif new_status == "done":
                done_count = sum(1 for t in current_plan if t["status"] == "done")
                total = len(current_plan)
                state_updates["current_activity"] = f"Done {done_count}/{total}: {task_label}"

        elif tool_name == "search_web" and isinstance(data, dict) and "results" in data:
            state_updates["search_results"] = data
            state_updates["current_activity"] = f'Searched: "{data.get("query", "")}"\''

        elif tool_name == "scrape_website" and isinstance(data, dict) and "content" in data:
            state_updates["scraped_content"] = data
            state_updates["current_activity"] = f'Scraped: {data.get("url", "")}'

    return state_updates
