"""
chat_node -- binds Python tools + CopilotKit frontend tools to the LLM.

AG-UI / CopilotKit automatically handles frontend tool dispatch via execute
callbacks on the client side. We only need to route Python (server-side)
tools through the LangGraph tools node. No special interception needed.

IMPORTANT: parallel_tool_calls=False is required when mixing frontend and
Python tools. Without it the LLM may emit both types in one AIMessage;
ToolNode only executes Python calls, leaving frontend calls without a
ToolMessage result and causing the LLM to loop.
"""
import json
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from .state import AgentState
from .llm import get_llm
from .tools import PYTHON_TOOLS

PYTHON_TOOL_NAMES = {t.name for t in PYTHON_TOOLS}

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

SYSTEM_PROMPT = """You are Syllabus AI — an expert course-creation assistant for educators.

Your job: build complete, beautifully structured course syllabi with rich, accurate lesson content.
You have both RESEARCH tools (Python-side) and COURSE-BUILDING tools (frontend-side).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — ALWAYS PLAN FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

plan_tasks(tasks: list[str])
  → Call this FIRST for any request with 2+ chapters.
  → Break work into concrete steps. Example:
    ["Search 'Python programming curriculum' terminology",
     "Scrape top result for vocabulary reference",
     "create_syllabus: python-beginners",
     "add_chapter: ch1-introduction",
     "add_lesson: l1-1-what-is-python",
     "add_lesson: l1-2-installation",
     "add_chapter: ch2-basics",
     ...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — RESEARCH (before writing any lesson)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

search_web(query, country="us", time_period="", num_results=6)
  → Search for: correct vocabulary, standard curriculum, definitions, examples.

scrape_website(url: str)
  → Get full markdown from a promising search result.
  → Use this content to write accurate, specific lesson blocks.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — BUILD THE COURSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

create_syllabus(id, title, subject, description?)
  → Call ONCE. id = url-friendly slug e.g. "python-beginners".

add_chapter(syllabusId, chapterId, title, description?)
  → Add all chapters before adding lessons.

add_lesson(chapterId, lessonId, title, content)
  → content = BlockNote JSON array (minimum 8 blocks).
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
  ✓ 1× paragraph        — engaging intro (3-5 sentences)
  ✓ 1-2× heading level 2 — section titles
  ✓ 3-5× paragraphs or bulletListItems — core content
  ✓ 1× numbered or bullet list — key takeaways or steps
  ✓ 1× paragraph — summary / bridge to next lesson

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
    "level": 1,
    "language": "python"
  },
  "content": [{ "type": "text", "text": "...", "styles": {} }],
  "children": []
}

STRICT RULES:
  1. Every id globally unique, prefixed with lessonId
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

async def chat_node(state: AgentState, config: RunnableConfig) -> dict:
    """Main LLM node -- builds prompt, calls LLM, updates state from tool results."""
    llm = get_llm()

    ck = state.get("copilotkit") or {}
    frontend_tools_raw = (
        ck.get("actions") or []
        if isinstance(ck, dict)
        else getattr(ck, "actions", None) or []
    )

    # parallel_tool_calls=False is CRITICAL when mixing frontend (AG-UI) and
    # Python tools. Without it the LLM may emit both in one AIMessage; ToolNode
    # only runs Python calls and the frontend calls are left without a
    # ToolMessage result, causing the LLM to loop until recursion limit.
    bound_llm = llm.bind_tools(
        [*PYTHON_TOOLS, *frontend_tools_raw],
        parallel_tool_calls=False,
    )

    messages = await _maybe_summarize(list(state["messages"]), llm)
    system = SystemMessage(content=SYSTEM_PROMPT)
    response = await bound_llm.ainvoke([system, *messages], config)

    updates: dict = {"messages": [response]}

    for msg in state["messages"]:
        if not isinstance(msg, ToolMessage):
            continue
        name = getattr(msg, "name", None) or ""
        content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)

        if name == "plan_tasks":
            try:
                updates["plan"] = json.loads(content)
            except Exception:
                pass
        elif name == "search_web":
            updates["search_results"] = content
        elif name == "scrape_website":
            updates["scraped_content"] = content

    return updates
