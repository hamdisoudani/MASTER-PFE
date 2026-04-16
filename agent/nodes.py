"""
chat_node -- binds Python tools + CopilotKit frontend tools to the LLM.

AG-UI / CopilotKit automatically handles frontend tool dispatch via execute
callbacks on the client side. We only need to route Python (server-side)
tools through the LangGraph tools node. No special interception needed.

IMPORTANT: parallel_tool_calls=False is required when mixing frontend and
Python tools. Without it the LLM may emit both types in one AIMessage;
ToolNode only executes Python calls, leaving frontend calls without a
ToolMessage result and causing the LLM to loop.

CONTEXT INJECTION:
  useCopilotReadable() on the frontend populates state.copilotkit["context"]
  as a list of {description, value} items. We read those here and inject them
  into the system prompt dynamically so the agent knows what already exists
  in the user's app (existing syllabuses, chapters, lessons, render errors).
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


# ─── System prompt template ───────────────────────────────────────────────────
# {{FRONTEND_CONTEXT}} is replaced at runtime with data from useCopilotReadable.
_SYSTEM_PROMPT_TEMPLATE = """You are Syllabus AI — an expert course-creation assistant for educators.

Your job: build complete, beautifully structured course syllabi with rich, accurate lesson content.
You have both RESEARCH tools (Python-side) and COURSE-BUILDING tools (frontend-side).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT APP STATE  (live data from the user's frontend)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{frontend_context}

RULES FOR USING THIS CONTEXT:
  • ALWAYS read this before creating anything.
  • NEVER create a syllabus, chapter, or lesson that already exists.
  • Use the exact IDs shown here when referencing existing content.
  • If renderErrors is non-empty → call update_lesson_content immediately
    to fix the broken lesson, then tell the user in one sentence.

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

update_plan_task(task_id, status)
  → Call update_plan_task(N, 'in_progress') BEFORE starting step N.
  → Call update_plan_task(N, 'done') AFTER completing step N.
  → This drives the live progress checklist the user sees.

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

{{
  "id": "<lessonId>-<unique-suffix>",
  "type": "heading|paragraph|bulletListItem|numberedListItem|codeBlock|quote",
  "props": {{
    "textColor": "default",
    "backgroundColor": "default",
    "textAlignment": "left",
    "level": 1,
    "language": "python"
  }},
  "content": [{{ "type": "text", "text": "...", "styles": {{}} }}],
  "children": []
}}

STRICT RULES:
  1. Every id globally unique, prefixed with lessonId
  2. "content" is ALWAYS an array — never null, never a plain string
  3. "children" is ALWAYS [] (empty array)
  4. heading MUST have "level": 1|2|3 in props
  5. codeBlock MUST have "language": "python"|"js"|"bash"|"sql"|... in props
  6. No extra keys beyond id, type, props, content, children

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE STYLE — CRITICAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After completing work, reply in 1-3 short, friendly sentences.
  ✓ "Done! I created the A1 syllabus with Chapter 1 and 4 lessons. Want me to continue with Chapter 2?"
  ✗ NEVER write formal reports, headers like "Summary:", bullet breakdowns of work, or word counts like "(98 words)".
  ✗ NEVER say "Research Done:", "Still Needs to Be Done:", "Syllabus Created:", etc.
  ✗ NEVER append "(N words)" or any word-count notation to your replies.
"""


def _format_context_items(context_items: list) -> str:
    """
    Format CopilotKit readable context items into a readable string for the
    system prompt. Each item is a dict with 'description' and 'value' keys,
    as produced by useCopilotReadable() on the React frontend.
    """
    if not context_items:
        return "(No frontend context available — user may have no syllabuses yet.)"

    sections = []
    for item in context_items:
        if not isinstance(item, dict):
            continue
        description = item.get("description", "Context")
        value = item.get("value", "")
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            value_str = str(value)
        sections.append(f"[ {description} ]\n{value_str}")

    return "\n\n".join(sections) if sections else "(No frontend context available.)"


def _build_system_prompt(state: AgentState) -> str:
    """
    Build the system prompt for this turn, injecting live frontend context
    from state.copilotkit["context"] (populated by useCopilotReadable hooks).
    """
    ck = state.get("copilotkit") or {}
    context_items = (
        ck.get("context", [])
        if isinstance(ck, dict)
        else getattr(ck, "context", None) or []
    )
    frontend_context = _format_context_items(context_items)
    return _SYSTEM_PROMPT_TEMPLATE.format(frontend_context=frontend_context)


def _apply_plan_updates(messages: list) -> list | None:
    """Reconstruct the latest plan state by replaying all plan_tasks and
    update_plan_task ToolMessages from history in order."""
    current_plan: list | None = None
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        name = getattr(msg, "name", None) or ""
        raw = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
        if name == "plan_tasks":
            try:
                current_plan = json.loads(raw)
            except Exception:
                pass
        elif name == "update_plan_task" and current_plan is not None:
            try:
                result = json.loads(raw)
                task_id = result.get("task_id")
                new_status = result.get("status")
                if task_id is not None and new_status:
                    current_plan = [
                        {**t, "status": new_status} if t["id"] == task_id else t
                        for t in current_plan
                    ]
            except Exception:
                pass
    return current_plan


async def chat_node(state: AgentState, config: RunnableConfig) -> dict:
    """Main LLM node -- builds prompt with live frontend context, calls LLM,
    updates state from tool results."""
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

    # Build system prompt with live frontend context injected
    system_prompt = _build_system_prompt(state)

    messages = await _maybe_summarize(list(state["messages"]), llm)
    system = SystemMessage(content=system_prompt)
    response = await bound_llm.ainvoke([system, *messages], config)

    updates: dict = {"messages": [response]}

    # Reconstruct plan state from full ToolMessage history (plan_tasks sets
    # the initial list; update_plan_task patches individual task statuses)
    rebuilt_plan = _apply_plan_updates(state["messages"])
    if rebuilt_plan is not None:
        updates["plan"] = rebuilt_plan

    # Update remaining state fields from the most recent matching ToolMessage
    for msg in reversed(state["messages"]):
        if not isinstance(msg, ToolMessage):
            continue
        name = getattr(msg, "name", None) or ""
        raw = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)

        if name == "search_web" and "search_results" not in updates:
            try:
                updates["search_results"] = json.loads(raw)
            except Exception:
                pass

        elif name == "scrape_website" and "scraped_content" not in updates:
            try:
                updates["scraped_content"] = json.loads(raw)
            except Exception:
                pass

        if "search_results" in updates and "scraped_content" in updates:
            break

    return updates
