"""
chat_node â binds Python tools + CopilotKit frontend tools to the LLM.

IMPORTANT: parallel_tool_calls=False is required when mixing frontend and
Python tools. Without it the LLM may emit both types in one AIMessage;
ToolNode only executes Python calls, leaving frontend calls without a
ToolMessage result and causing the LLM to loop.

CONTEXT INJECTION:
  useCopilotReadable() on the frontend serializes the value to a JSON string,
  then stores {description, value} into state.copilotkit["context"]. We read
  those here, parse the JSON string back, and inject everything into the
  system prompt so the agent sees the current editor state on every turn.
"""
import json
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode
from copilotkit.langchain import copilotkit_emit_state

from .state import AgentState, PlanStep
from .llm import get_llm
from .tools import PYTHON_TOOLS, PYTHON_TOOL_NAMES, PLAN_TOOL_NAMES

MAX_MESSAGES = 30
KEEP_RECENT = 14


async def _maybe_summarize(messages: list, llm) -> list:
    """Compress old messages when the conversation gets long."""
    if len(messages) <= MAX_MESSAGES:
        return messages

    to_compress = messages[:-KEEP_RECENT]
    recent = messages[-KEEP_RECENT:]

    lines = []
    for m in to_compress:
        role = getattr(m, "type", "msg")
        raw = m.content if isinstance(m.content, str) else json.dumps(m.content)[:300]
        lines.append(f"[{role}] {raw[:250]}")

    summary_req = HumanMessage(
        content=(
            "Summarise the conversation so far in <= 120 words, preserving key"
            " decisions, tool results, and open questions:

"
            + "
".join(lines)
        )
    )
    summary_msg = await llm.ainvoke([summary_req])
    summary_text = (
        summary_msg.content
        if isinstance(summary_msg.content, str)
        else json.dumps(summary_msg.content)
    )
    return [SystemMessage(content=f"[Conversation summary]
{summary_text}")] + recent


def _build_system_prompt(state: AgentState) -> str:
    """Build the full system prompt with context injection."""
    base = (
        "You are an expert course-creation assistant.
"
        "Your job is to help users build rich, well-structured syllabuses.

"
        "## How you work
"
        "1. When the user asks you to create a syllabus, first call `set_plan` with all steps.
"
        "2. Execute each step in order. For search steps, call `web_search` / `scrape_page`.
"
        "3. Use the frontend tools to build the syllabus structure and content.
"
        "4. Call `mark_step_done` after completing each step.

"
        "## Tools available
"
        "### Frontend tools (dispatched automatically by CopilotKit)
"
        "- create_syllabus(id, title, subject, description?)
"
        "- add_chapter(syllabusId, chapterId, title, description?)
"
        "- add_lesson(chapterId, lessonId, title, content)
"
        "- update_lesson_content(lessonId, content)
"
        "- remove_chapter(chapterId)
"
        "- remove_lesson(lessonId)
"
        "- report_render_error(lessonId, error)

"
        "### Server-side tools
"
        "- set_plan(steps) -> create execution plan
"
        "- mark_step_done(step_id) -> mark step complete
"
        "- web_search(query) -> search the web
"
        "- scrape_page(url) -> scrape a page

"
        "## BlockNote content format
"
        "Every lesson's `content` field must be a valid BlockNote JSON array.
"
        "Each block:
"
        "  { type, props?, content?, children? }

"
        "Supported block types and their props:
"
        "  paragraph          - props: textAlignment
"
        "  heading            - props: level (1|2|3), textAlignment
"
        "  bulletListItem     - props: textAlignment
"
        "  numberedListItem   - props: textAlignment
"
        "  checkListItem      - props: checked (bool), textAlignment
"
        "  table              - content: tableContent (see below)
"
        "  image              - props: url, caption, textAlignment
"
        "  video              - props: url, caption, textAlignment
"
        "  audio              - props: url, caption
"
        "  file               - props: url, name, caption
"
        "  codeBlock          - props: language

"
        "Inline content array (used in most block types):
"
        "  { type: 'text', text: '..', styles?: { bold, italic, underline,
"
        "    strikethrough, code, textColor, backgroundColor } }
"
        "  { type: 'link', href: '..', content: [text nodes] }

"
        "Table format:
"
        "  content: { type: 'tableContent', rows: [
"
        "    { cells: [ [inlineContent], ... ] }
"
        "  ]}

"
        "RULES:
"
        "1. NEVER output plain text outside a block.
"
        "2. Always use inline content arrays for text-bearing blocks.
"
        "3. Use heading level 2 for section titles, level 3 for sub-sections.
"
        "4. Keep lessons focused; split large topics into multiple lessons.
"
        "5. Do NOT wrap the JSON in markdown fences.
"
    )

    ctx_entries: list = state.get("copilotkit", {}).get("context", [])
    if ctx_entries:
        ctx_lines = ["## Current editor state"]
        for entry in ctx_entries:
            desc = entry.description if hasattr(entry, "description") else entry.get("description", "")
            raw = entry.value if hasattr(entry, "value") else entry.get("value", "[]")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                value_str = json.dumps(parsed, indent=2)
            except Exception:
                value_str = str(raw)
            ctx_lines.append(f"### {desc}")
            ctx_lines.append(value_str)
        base += "
" + "
".join(ctx_lines)

    plan = state.get("plan", [])
    if plan:
        plan_lines = ["
## Current plan"]
        for step in plan:
            status_icon = {"pending": "waiting", "in_progress": "active", "searching": "searching", "done": "done"}.get(step.get("status", ""), "?")
            plan_lines.append(f"  [{status_icon}] Step {step.get('id', '?')}: [{step.get('type', '?')}] {step.get('title', '')}")
        base += "
".join(plan_lines)

    scraped = state.get("scraped_pages", [])
    if scraped:
        base += "

## Research results (scraped pages)
"
        for page in scraped[-6:]:
            base += f"### {page.get('title', page.get('url', ''))}
"
            base += f"URL: {page.get('url', '')}
"
            md = page.get("markdown", "")
            base += md[:3000] + ("
[truncated]" if len(md) > 3000 else "") + "

"

    return base


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Main chat node with system prompt, frontend+server tools, inline plan handling."""
    llm = get_llm()

    copilotkit_config = state.get("copilotkit", {})
    frontend_tools = copilotkit_config.get("actions", [])
    all_tools = frontend_tools + PYTHON_TOOLS

    bound = llm.bind_tools(all_tools, parallel_tool_calls=False)

    messages = list(state.get("messages", []))
    messages = await _maybe_summarize(messages, llm)

    system_prompt = _build_system_prompt(state)
    full_messages = [SystemMessage(content=system_prompt)] + messages

    response: AIMessage = await bound.ainvoke(full_messages, config)

    new_plan = list(state.get("plan", []))
    current_index = state.get("currentStepIndex", 0)
    plan_status = state.get("planStatus", "idle")
    activity = state.get("current_activity", "")
    finished = state.get("finished", False)

    tool_messages: list[ToolMessage] = []
    has_python_calls = False
    has_frontend_calls = False

    if response.tool_calls:
        for tc in response.tool_calls:
            name = tc["name"]
            args = tc["args"]

            if name == "set_plan":
                steps_input = args.get("steps", [])
                new_plan = [
                    PlanStep(
                        id=i,
                        type=s.get("type", "task"),
                        title=s.get("title", s.get("description", "")),
                        status="pending",
                        queries=s.get("queries"),
                        search_data=None,
                    )
                    for i, s in enumerate(steps_input)
                ]
                if new_plan:
                    new_plan[0] = {**new_plan[0], "status": "in_progress"}
                current_index = 0
                plan_status = "in_progress"
                activity = f"Plan created with {len(new_plan)} steps"
                tool_messages.append(
                    ToolMessage(content="Plan set successfully.", tool_call_id=tc["id"])
                )

            elif name == "mark_step_done":
                idx = args.get("step_id", current_index)
                if 0 <= idx < len(new_plan):
                    new_plan[idx] = {**new_plan[idx], "status": "done"}
                next_idx = idx + 1
                if next_idx >= len(new_plan):
                    plan_status = "done"
                    finished = True
                    current_index = next_idx
                    activity = "All steps completed"
                else:
                    new_plan[next_idx] = {**new_plan[next_idx], "status": "in_progress"}
                    current_index = next_idx
                    activity = f"Step {idx} done, starting step {next_idx}"
                tool_messages.append(
                    ToolMessage(content="Step marked done.", tool_call_id=tc["id"])
                )

            elif name in PYTHON_TOOL_NAMES:
                has_python_calls = True
            else:
                has_frontend_calls = True

    updated: dict[str, Any] = {
        "messages": [response, *tool_messages],
        "plan": new_plan,
        "currentStepIndex": current_index,
        "planStatus": plan_status,
        "current_activity": activity,
        "finished": finished,
    }

    await copilotkit_emit_state(state, updated)
    return updated


async def search_node(state: AgentState) -> dict[str, Any]:
    """Run search queries for the current pending search step."""
    from .search import run_search_step

    steps = list(state.get("plan", []))
    idx = state.get("currentStepIndex", 0)

    if idx >= len(steps):
        return {}

    step = steps[idx]
    queries = step.get("queries") or []
    results = await run_search_step(queries)

    steps[idx] = {**step, "status": "searching", "search_data": results}

    updated: dict[str, Any] = {
        "plan": steps,
        "search_results": results,
        "current_activity": f"Searching: {queries[0] if queries else ''}",
    }
    await copilotkit_emit_state(state, updated)
    return updated


async def scraper_node(state: AgentState) -> dict[str, Any]:
    """Scrape top URLs from the last search results."""
    from .search import scrape_selected

    search_data = state.get("search_results", [])
    scraped = await scrape_selected(search_data)

    steps = list(state.get("plan", []))
    idx = state.get("currentStepIndex", 0)

    if 0 <= idx < len(steps):
        steps[idx] = {**steps[idx], "status": "done", "search_data": search_data}

    next_idx = idx + 1
    plan_status = state.get("planStatus", "in_progress")
    if next_idx < len(steps):
        steps[next_idx] = {**steps[next_idx], "status": "in_progress"}
    else:
        plan_status = "done"

    updated: dict[str, Any] = {
        "plan": steps,
        "scraped_pages": state.get("scraped_pages", []) + scraped,
        "search_results": search_data,
        "currentStepIndex": next_idx,
        "planStatus": plan_status,
        "current_activity": f"Scraped {len(scraped)} pages",
    }
    await copilotkit_emit_state(state, updated)
    return updated


def route_after_chat(state: AgentState) -> str:
    """Route after chat_node: python tools, search subgraph, or end."""
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []

    python_non_plan = [tc for tc in tool_calls if tc["name"] in PYTHON_TOOL_NAMES and tc["name"] not in PLAN_TOOL_NAMES]
    if python_non_plan:
        return "tools"

    plan = state.get("plan", [])
    current_index = state.get("currentStepIndex", 0)
    if 0 <= current_index < len(plan):
        step = plan[current_index]
        if step.get("type") == "search" and step.get("status") == "in_progress" and step.get("queries"):
            return "search_subgraph"

    plan_calls = [tc for tc in tool_calls if tc["name"] in PLAN_TOOL_NAMES]
    if plan_calls:
        return "chat_node"

    return "end"


python_tools_node = ToolNode([t for t in PYTHON_TOOLS if t.name not in PLAN_TOOL_NAMES])
