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
  useAgentContext() (or useCopilotReadable) on the frontend serializes the
  value to a JSON string, then stores {description, value_as_json_string}
  into state.copilotkit["context"].  We read those here, parse the JSON
  string back, and inject everything into the system prompt so the agent
  sees the current editor state on every turn.

  Access pattern (from CopilotKit SDK source):
    state["copilotkit"]["context"]  →  List[{description: str, value: str}]
  where value is always JSON.stringify()'d on the frontend.
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
            "Summarise the conversation so far in ≤ 120 words, preserving key"
            " decisions, tool results, and open questions:\n\n"
            + "\n".join(lines)
        )
    )
    summary_msg = await llm.ainvoke([summary_req])
    summary_text = (
        summary_msg.content
        if isinstance(summary_msg.content, str)
        else json.dumps(summary_msg.content)
    )
    return [SystemMessage(content=f"[Conversation summary]\n{summary_text}")] + recent


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
        "- web_search(query) → returns search results\n"
        "- scrape_page(url) → returns page content\n\n"
        "## BlockNote content format\n"
        "Every lesson\'s `content` field must be a valid BlockNote JSON array.\n"
        "Each block:\n"
        "  { type, props?, content?, children? }\n\n"
        "Supported block types and their props:\n"
        "  paragraph          – props: textAlignment\n"
        "  heading            – props: level (1|2|3), textAlignment\n"
        "  bulletListItem     – props: textAlignment\n"
        "  numberedListItem   – props: textAlignment\n"
        "  checkListItem      – props: checked (bool), textAlignment\n"
        "  table              – content: tableContent (see below)\n"
        "  image              – props: url, caption, textAlignment\n"
        "  video              – props: url, caption, textAlignment\n"
        "  audio              – props: url, caption\n"
        "  file               – props: url, name, caption\n"
        "  codeBlock          – props: language\n\n"
        "Inline content array (used in most block types):\n"
        "  { type: \'text\', text: \'..\', styles?: { bold, italic, underline,\n"
        "    strikethrough, code, textColor, backgroundColor } }\n"
        "  { type: \'link\', href: \'..\', content: [text nodes] }\n\n"
        "Table format:\n"
        "  content: { type: \'tableContent\', rows: [\n"
        "    { cells: [ [inlineContent], ... ] }\n"
        "  ]}\n\n"
        "RULES:\n"
        "1. NEVER output plain text outside a block.\n"
        "2. Always use inline content arrays for text-bearing blocks.\n"
        "3. Use heading level 2 for section titles, level 3 for sub-sections.\n"
        "4. Keep lessons focused; split large topics into multiple lessons.\n"
        "5. Do NOT wrap the JSON in markdown fences.\n"
    )

    ctx_entries: list = state.get("copilotkit", {}).get("context", [])
    if ctx_entries:
        ctx_lines = ["## Current editor state"]
        for entry in ctx_entries:
            desc  = entry.get("description", "")
            raw   = entry.get("value", "[]")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                value_str = json.dumps(parsed, indent=2)
            except Exception:
                value_str = str(raw)
            ctx_lines.append(f"### {desc}")
            ctx_lines.append(value_str)
        base += "\n" + "\n".join(ctx_lines)

    return base


async def chat_node(state: AgentState, config: RunnableConfig) -> AgentState:
    llm = get_llm(config)

    copilotkit_config = state.get("copilotkit", {})
    all_tools         = copilotkit_config.get("actions", []) + PYTHON_TOOLS

    bound = llm.bind_tools(
        all_tools,
        parallel_tool_calls=False,
    )

    messages = list(state.get("messages", []))
    messages = await _maybe_summarize(messages, llm)

    system_prompt = _build_system_prompt(state)
    full_messages = [SystemMessage(content=system_prompt)] + messages

    response = await bound.ainvoke(full_messages, config)
    return {"messages": messages + [response]}


def route_node(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []

    python_calls  = [tc for tc in tool_calls if tc["name"] in PYTHON_TOOL_NAMES]
    frontend_calls = [tc for tc in tool_calls if tc["name"] not in PYTHON_TOOL_NAMES]

    if python_calls:
        return "tools"
    if frontend_calls:
        return "end"
    return "end"
