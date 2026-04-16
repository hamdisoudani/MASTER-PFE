# nodes.py — see module docstring below
"""
chat_node  -- main LLM node.
  - Binds Python tools + CopilotKit frontend tools to the LLM.
  - Summarization middleware compresses old messages when history > MAX_MESSAGES.
  - Extracts ToolMessage results and persists them into named state fields
    so the frontend can render plan / search / scrape live.

tools_node -- smart tool executor.
  - Runs Python (server-side) tool calls via LangGraph ToolNode.
  - For frontend (browser-side) tool calls, injects a ToolMessage using the
    ag-ui orphan format:  "Tool call '<name>' with id '<id>' was interrupted
    before completion."  ag-ui detects this pattern on the next request and
    replaces it with the real result returned by the frontend execute callback.
  - This is the correct CopilotKit/ag-ui pattern — no synthetic "acknowledged"
    placeholders that confuse the LLM and no separate pre_tools node.
"""
import json
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .llm import get_llm
from .tools import PYTHON_TOOLS

_python_tool_node = ToolNode(PYTHON_TOOLS)
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

WORKFLOW RULES -- follow these exactly:
1. Always start by calling plan_tasks to break the user request into clear sub-tasks.
2. For each sub-task that needs content, use search_web / scrape_website to gather material.
3. Call create_syllabus ONCE before adding any chapters or lessons.
4. Add chapters and lessons in order with add_chapter / add_lesson.
5. After completing all tasks, stop and summarise what was built for the user.
6. NEVER call the same tool twice with identical arguments in the same conversation turn.
7. NEVER call a frontend tool (create_syllabus, add_chapter, add_lesson, etc.) unless
   research for that section is already done.
8. If a tool result says the action was "interrupted before completion", that means it was
   sent to the frontend for execution -- do NOT retry it; continue with the next task.
"""


async def chat_node(state: AgentState, config: RunnableConfig) -> dict:
    """Main LLM node -- builds prompt, calls LLM, updates state from tool results."""
    llm = get_llm()

    # Build tool list: Python tools + frontend tool schemas from copilotkit state
    ck = state.get("copilotkit") or {}
    frontend_tools_raw = (
        ck.get("actions") or []
        if isinstance(ck, dict)
        else getattr(ck, "actions", None) or []
    )
    bound_llm = llm.bind_tools([*PYTHON_TOOLS, *frontend_tools_raw])

    messages = await _maybe_summarize(list(state["messages"]), llm)

    system = SystemMessage(content=SYSTEM_PROMPT)
    response = await bound_llm.ainvoke([system, *messages], config)

    # Extract tool results from previous ToolMessages and update state fields
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


async def tools_node(state: AgentState) -> dict:
    """
    Execute server-side (Python) tools and handle frontend tool calls correctly.

    For frontend tool calls we inject a ToolMessage using ag-ui's orphan format:
        "Tool call '<name>' with id '<id>' was interrupted before completion."
    ag-ui detects this exact pattern on the NEXT request and replaces it with
    the actual result returned by the frontend execute callback -- giving the
    LLM the real tool output on the following turn without any confusion.
    """
    last = state["messages"][-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return {}

    backend_calls  = [tc for tc in last.tool_calls if tc.get("name") in PYTHON_TOOL_NAMES]
    frontend_calls = [tc for tc in last.tool_calls if tc.get("name") not in PYTHON_TOOL_NAMES]

    result_messages: list = []

    # Run Python tools -- filter the AIMessage to only backend calls so ToolNode
    # does not attempt (and fail) to execute frontend tool calls.
    if backend_calls:
        filtered_last  = last.model_copy(update={"tool_calls": backend_calls})
        filtered_state = {**state, "messages": [*state["messages"][:-1], filtered_last]}
        tool_result    = await _python_tool_node.ainvoke(filtered_state)
        result_messages.extend(tool_result.get("messages", []))

    # Inject ag-ui orphan ToolMessages for frontend calls.
    # ag-ui will replace these placeholders with the real execute-callback results
    # when the frontend sends back ToolCallResult events on the next request.
    for tc in frontend_calls:
        tc_name = tc.get("name", "unknown")
        tc_id   = tc.get("id", "")
        result_messages.append(
            ToolMessage(
                content=f"Tool call '{tc_name}' with id '{tc_id}' was interrupted before completion.",
                tool_call_id=tc_id,
                name=tc_name,
            )
        )

    return {"messages": result_messages} if result_messages else {}
