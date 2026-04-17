from __future__ import annotations
import json
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from .state import AgentState
from .llm import get_llm
from .tools import (
    PYTHON_TOOLS,
    PYTHON_TOOL_NAMES,
    _exec_plan_tasks,
    _exec_update_plan_task,
    _exec_search_web,
    _exec_scrape_website,
)

MAX_MESSAGES = 30
KEEP_RECENT  = 14


async def _maybe_summarize(messages: list, llm) -> tuple[list, list]:
    if len(messages) <= MAX_MESSAGES:
        return messages, []

    to_compress = messages[:-KEEP_RECENT]
    recent      = messages[-KEEP_RECENT:]

    lines = []
    for m in to_compress:
        role = getattr(m, "type", "msg")
        raw  = m.content if isinstance(m.content, str) else json.dumps(m.content)[:300]
        lines.append(f"[{role}] {raw[:250]}")

    summary_req = HumanMessage(
        content=(
            "Summarise the conversation so far in <= 120 words, preserving key "
            "decisions, tool results, and open questions:\n\n" + "\n".join(lines)
        )
    )
    resp         = await llm.ainvoke([summary_req])
    summary_text = resp.content if isinstance(resp.content, str) else json.dumps(resp.content)
    summary_msg  = SystemMessage(content=f"[Conversation summary]\n{summary_text}")

    removes     = [RemoveMessage(id=m.id) for m in to_compress if getattr(m, "id", None)]
    state_delta = removes + [summary_msg]

    return [summary_msg] + list(recent), state_delta


def _build_system_prompt(state: AgentState) -> str:
    base = (
        "You are an expert course-creation assistant.\n"
        "Your job is to help users build rich, well-structured syllabuses.\n\n"
        "## Tools available\n"
        "### Frontend tools (dispatched automatically by CopilotKit)\n"
        "- create_syllabus(id, title, subject, description?)\n"
        "- add_chapter(syllabusId, chapterId, title, description?)\n"
        "- add_lesson(chapterId, lessonId, title, content)\n"
        "- update_lesson_content(lessonId, content)\n"
        "- remove_chapter(chapterId)\n"
        "- remove_lesson(lessonId)\n"
        "- report_render_error(lessonId, error)\n\n"
        "### Python tools (executed server-side)\n"
        "- plan_tasks(tasks)              creates the live progress checklist\n"
        "- update_plan_task(id, status)   updates step status (pending|in_progress|done)\n"
        "- search_web(query)              web search via Serper\n"
        "- scrape_website(url)            full page markdown\n\n"
        "## Workflow rule\n"
        "For any request with 2+ chapters:\n"
        "  1. Call plan_tasks([...steps...]) FIRST\n"
        "  2. Before each step call update_plan_task(id, 'in_progress')\n"
        "  3. After each step call update_plan_task(id, 'done')\n"
        "  4. Use search_web / scrape_website before writing lesson content\n\n"
        "## BlockNote content format\n"
        "Every lesson content must be a valid BlockNote JSON array.\n"
        "Each block: { type, props?, content?, children? }\n\n"
        "Supported types: paragraph, heading (level 1|2|3), bulletListItem,\n"
        "numberedListItem, checkListItem (checked: bool), table, codeBlock\n\n"
        "Inline content: { type: 'text', text: '...', styles?: {bold, italic, ...} }\n\n"
        "RULES:\n"
        "1. NEVER output plain text outside a block.\n"
        "2. Always use inline content arrays for text-bearing blocks.\n"
        "3. Do NOT wrap the JSON in markdown fences.\n"
    )

    ctx_entries: list = state.get("copilotkit", {}).get("context", [])
    if ctx_entries:
        ctx_lines = ["\n## Current editor state"]
        for entry in ctx_entries:
            desc      = entry.description if hasattr(entry, "description") else entry.get("description", "")
            raw       = entry.value if hasattr(entry, "value") else entry.get("value", "[]")
            try:
                parsed    = json.loads(raw) if isinstance(raw, str) else raw
                value_str = json.dumps(parsed, indent=2)
            except Exception:
                value_str = str(raw)
            ctx_lines.append(f"### {desc}")
            ctx_lines.append(value_str)
        base += "\n".join(ctx_lines)

    return base


async def chat_node(state: AgentState, config: RunnableConfig) -> dict:
    llm = get_llm(config)

    copilotkit_config = state.get("copilotkit", {})
    all_tools         = copilotkit_config.get("actions", []) + PYTHON_TOOLS

    bound = llm.bind_tools(all_tools, parallel_tool_calls=False)

    messages                  = list(state.get("messages", []))
    context_msgs, state_delta = await _maybe_summarize(messages, llm)

    system_prompt = _build_system_prompt(state)
    full_messages = [SystemMessage(content=system_prompt)] + context_msgs

    response = await bound.ainvoke(full_messages, config)

    return {"messages": state_delta + [response]}


async def python_tools_node(state: AgentState, config: RunnableConfig) -> dict:
    last        = state["messages"][-1]
    tool_calls  = [tc for tc in (getattr(last, "tool_calls", None) or [])
                   if tc["name"] in PYTHON_TOOL_NAMES]

    if not tool_calls:
        return {}

    new_messages: list = []
    updates: dict      = {}

    for tc in tool_calls:
        name = tc["name"]
        args = tc["args"]
        tid  = tc["id"]

        if name == "plan_tasks":
            content, state_updates = await _exec_plan_tasks(args.get("tasks", []))

        elif name == "update_plan_task":
            content, state_updates = await _exec_update_plan_task(
                task_id      = args.get("task_id", 0),
                status       = args.get("status", "pending"),
                current_plan = state.get("plan") or [],
            )

        elif name == "search_web":
            content, state_updates = await _exec_search_web(
                query       = args.get("query", ""),
                country     = args.get("country", "us"),
                time_period = args.get("time_period", ""),
                num_results = args.get("num_results", 6),
            )

        elif name == "scrape_website":
            content, state_updates = await _exec_scrape_website(url=args.get("url", ""))

        else:
            content       = json.dumps({"error": f"Unknown tool: {name}"})
            state_updates = {}

        new_messages.append(ToolMessage(content=content, tool_call_id=tid))
        updates.update(state_updates)

    return {"messages": new_messages, **updates}
